import importlib
from typing import Any

from django.template import Template
from django.template.base import NodeList, VariableNode
from django.template.loader import get_template, render_to_string
from emails.api.emails_config import EMAILS_CONFIG
from emails.models import DynamicTemplate


def extract_from_nodes(nodelist):
    variables = set()
    for node in nodelist:
        if isinstance(node, VariableNode):
            variables.update(token.strip() for token in node.filter_expression.token.split("|")[0].split("."))
        elif hasattr(node, "nodelist"):
            variables.update(extract_from_nodes(node.nodelist))
        elif isinstance(node, NodeList):
            variables.update(extract_from_nodes(node))
    return variables


def extract_variables_from_template(template_name):
    template = get_template(template_name)
    variables = extract_from_nodes(template.template.nodelist)
    return variables


def extract_variables_from_subject(subject):
    template = Template(subject)
    variables = extract_from_nodes(template.nodelist)
    return variables


def get_full_dynamic_template_info(template_name):
    # oly for dynamic template
    dynamic_template = DynamicTemplate.objects.get(template_name=template_name)
    template = dynamic_template.template
    subject = dynamic_template.subject

    exclude_vars = ["BASE_URL"]
    variables = extract_variables_from_subject(template)
    subject_vars = extract_variables_from_subject(subject)

    variables.update(subject_vars)
    variables = [var for var in variables if var not in exclude_vars]

    dependancies = set()
    for param in variables:
        dependancies.update(EMAILS_CONFIG.parameters[param].depends_on)

    dependancies = list(dependancies)
    dep_data = []
    for dep in dependancies:
        if dep.startswith("context."):
            param_name = dep.split(".")[1]
            dep_data.append({"id": dep, "query_id_field": param_name, "context_dependent": True})
        else:
            dep_data.append({"id": dep, "query_id_field": EMAILS_CONFIG.dependencies[dep].query_id_field})

    return {"params": list(variables), "dependencies": dep_data, "template": template, "subject": subject}


def get_full_template_info(template_config):
    exclude_vars = ["BASE_URL"]
    variables = extract_variables_from_template(template_config.template)
    subject_vars = extract_variables_from_subject(template_config.subject)
    variables.update(subject_vars)
    variables = [var for var in variables if var not in exclude_vars]

    dependancies = set()
    for param in variables:
        dependancies.update(EMAILS_CONFIG.parameters[param].depends_on)

    dependancies = list(dependancies)
    dep_data = []
    for dep in dependancies:
        if dep.startswith("context."):
            param_name = dep.split(".")[1]
            dep_data.append({"id": dep, "query_id_field": param_name, "context_dependent": True})
        else:
            dep_data.append({"id": dep, "query_id_field": EMAILS_CONFIG.dependencies[dep].query_id_field})

    return {
        "config": template_config.to_dict(),
        "params": list(variables),
        "dependencies": dep_data,
        "view": "/matching/emails/templates/" + template_config.id + "/",
    }


def render_template_to_html(template_path, context):
    return render_to_string(template_path, context)


class UnknownParameterException(Exception):
    pass


class MissingContextDependencyException(Exception):
    pass


class UnknownEmailTemplateException(Exception):
    pass


def _resolve_dependency_values(dependency_model_overrides=None, **context):
    dependency_model_overrides = dependency_model_overrides or {}
    dependency_values = {}
    for dependency_id, dependency_config in EMAILS_CONFIG.dependencies.items():
        if dependency_id == "context":
            continue

        dependency_query_value = context.get(dependency_config.query_id_field)
        if not dependency_query_value:
            dependency_values[dependency_id] = None
            continue

        if not dependency_config.model_source:
            dependency_values[dependency_id] = dependency_query_value
            continue

        model_or_loader = dependency_model_overrides.get(dependency_id)
        if model_or_loader is None:
            model_source = dependency_config.model_source.split(".")
            model_module = importlib.import_module(".".join(model_source[:-1]))
            model_or_loader = getattr(model_module, model_source[-1])
        model: Any = model_or_loader() if callable(model_or_loader) else model_or_loader
        dependency_values[dependency_id] = model.objects.get(id=dependency_query_value)

    return dependency_values


def prepare_dynamic_template_context(template_name, user_id=None, match_id=None, proposed_match_id=None, **kwargs):
    params = EMAILS_CONFIG.parameters
    dynamic_template_info = get_full_dynamic_template_info(template_name)

    template_params = dynamic_template_info["params"]

    available_dependencies = []

    dependency_values = _resolve_dependency_values(
        user_id=user_id,
        match_id=match_id,
        proposed_match_id=proposed_match_id,
        **kwargs,
    )
    for dependency_id, dependency_value in dependency_values.items():
        if dependency_value is not None:
            available_dependencies.append(dependency_id)

    for key in kwargs:
        available_dependencies.append(f"context.{key}")

    context = {}

    # 1 - check if all params are present & their dependenciencies are met
    for param in template_params:
        if param not in params:
            raise UnknownParameterException(f"Unknown parameter {param}")

        param_config = params[param]

        if not set(param_config.depends_on).issubset(available_dependencies):
            raise MissingContextDependencyException(
                f"Missing context dependency for {param} in {available_dependencies} - {param_config.depends_on}"
            )

        function_lookup = param_config.lookup
        function_lookup = function_lookup.split(".")
        module = importlib.import_module(".".join(function_lookup[:-1]))
        lookup_function = getattr(module, function_lookup[-1])

        lookup_context = {}
        for dependency in param_config.depends_on:
            if dependency in dependency_values and dependency_values[dependency] is not None:
                lookup_context[dependency] = dependency_values[dependency]
            elif dependency.startswith("context."):
                context_key = dependency.split(".")[1]
                assert context_key in kwargs, f"Missing context dependency in **kwargs for {param}"
                if "context" not in lookup_context:
                    lookup_context["context"] = {}
                lookup_context["context"][context_key] = kwargs[context_key]

        # Perform the lookup injecting all dependencies
        context[param] = lookup_function(**lookup_context)
    return dynamic_template_info, context


def prepare_template_context(
    template_name, user_id=None, match_id=None, proposed_match_id=None, retrieve_user_model=None, **kwargs
):
    params = EMAILS_CONFIG.parameters
    template_config = EMAILS_CONFIG.emails.get(template_name)
    if template_config is None:
        raise UnknownEmailTemplateException(f"Unknown email template '{template_name}'")

    template_info = get_full_template_info(template_config)
    template_params = template_info["params"]

    available_dependencies = []

    dependency_values = _resolve_dependency_values(
        dependency_model_overrides={"user": retrieve_user_model} if retrieve_user_model else None,
        user_id=user_id,
        match_id=match_id,
        proposed_match_id=proposed_match_id,
        **kwargs,
    )
    for dependency_id, dependency_value in dependency_values.items():
        if dependency_value is not None:
            available_dependencies.append(dependency_id)

    for key in kwargs:
        available_dependencies.append(f"context.{key}")

    context = {}

    # 1 - check if all params are present & their dependenciencies are met
    for param in template_params:
        if param not in params:
            raise UnknownParameterException(f"Unknown parameter {param}")

        param_config = params[param]

        if False and (not set(param_config.depends_on).issubset(available_dependencies)):
            # Currently disabled features, as we have some params with 'optional' dependencies and have no way to mark them as such yet
            raise MissingContextDependencyException(
                f"Missing context dependency for {param} in {available_dependencies} - {param_config.depends_on}"
            )

        function_lookup = param_config.lookup
        function_lookup = function_lookup.split(".")
        module = importlib.import_module(".".join(function_lookup[:-1]))
        lookup_function = getattr(module, function_lookup[-1])

        lookup_context = {}
        for dependency in param_config.depends_on:
            if dependency in dependency_values and dependency_values[dependency] is not None:
                lookup_context[dependency] = dependency_values[dependency]
            elif dependency.startswith("context."):
                context_key = dependency.split(".")[1]
                # assert context_key in kwargs, f"Missing context dependency in **kwargs for {param}" TODO: check disabled as we have vars with optional dependencies now
                if "context" not in lookup_context:
                    lookup_context["context"] = {}
                if context_key in kwargs:
                    lookup_context["context"][context_key] = kwargs[context_key]
                else:
                    lookup_context["context"][context_key] = None

        # Perform the lookup injecting all dependencies
        context[param] = lookup_function(**lookup_context)
    return template_info, context


def render_template_dynamic_lookup(template_name, user_id=None, match_id=None, proposed_match_id=None, **kwargs):
    template_info, context = prepare_template_context(template_name, user_id, match_id, proposed_match_id, **kwargs)
    template_path = template_info["config"]["template"]

    return render_template_to_html(template_path, context)
