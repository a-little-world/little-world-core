from management.models.matches import Match
from django.contrib.auth import get_user_model
from emails.api.emails_config import EMAILS_CONFIG
from django.template.loader import get_template, render_to_string
from django.template.base import VariableNode, NodeList
from management.models.unconfirmed_matches import ProposedMatch
from django.template import Template, Context
from emails.models import DynamicTemplate
import importlib


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

    return {"config": template_config.to_dict(), "params": list(variables), "dependencies": dep_data, "view": "/matching/emails/templates/" + template_config.id + "/"}


def render_template_to_html(template_path, context):
    return render_to_string(template_path, context)


class UnknownParameterException(Exception):
    pass


class MissingContextDependencyException(Exception):
    pass

def prepare_dynamic_template_context(template_name, user_id=None, match_id=None, proposed_match_id=None, **kwargs):
    params = EMAILS_CONFIG.parameters
    dynamic_template_info = get_full_dynamic_template_info(template_name)

    template_params = dynamic_template_info["params"]

    available_dependencies = []

    user = None if (not user_id) else get_user_model().objects.get(id=user_id)
    proposed_match = None if (not proposed_match_id) else ProposedMatch.objects.get(id=proposed_match_id)
    match = None if (not match_id) else Match.objects.get(id=match_id)
    
    print("user", user, "match", match, "proposed_match", proposed_match)

    if user:
        available_dependencies.append("user")

    if match:
        available_dependencies.append("match")
        
    if proposed_match:
        available_dependencies.append("proposed_match")

    for key in kwargs:
        available_dependencies.append(f"context.{key}")

    context = {}

    # 1 - check if all params are present & their dependenciencies are met
    for param in template_params:
        if param not in params:
            raise UnknownParameterException(f"Unknown parameter {param}")

        param_config = params[param]
        if not param_config.depends_on:
            continue

        if not set(param_config.depends_on).issubset(available_dependencies):
            raise MissingContextDependencyException(f"Missing context dependency for {param} in {available_dependencies} - {param_config.depends_on}")

        function_lookup = param_config.lookup
        function_lookup = function_lookup.split(".")
        module = importlib.import_module(".".join(function_lookup[:-1]))
        lookup_function = getattr(module, function_lookup[-1])

        lookup_context = {}
        for dependency in param_config.depends_on:
            param_name = param
            if dependency == "user":
                lookup_context["user"] = user
            elif dependency == "match":
                lookup_context["match"] = match
            elif dependency == "proposed_match":
                lookup_context["proposed_match"] = proposed_match
            elif dependency.startswith("context."):
                param_name = dependency.split(".")[1]
                print(kwargs)
                assert param_name in kwargs, f"Missing context dependency in **kwargs for {param}"
                if "context" not in lookup_context:
                    lookup_context["context"] = {}
                lookup_context["context"][param_name] = kwargs[param_name]

        # Perform the lookup injecting all dependencies
        context[param_name] = lookup_function(**lookup_context)
    return dynamic_template_info, context

def prepare_template_context(template_name, user_id=None, match_id=None, proposed_match_id=None, **kwargs):
    params = EMAILS_CONFIG.parameters
    template_config = EMAILS_CONFIG.emails.get(template_name)
    template_path = template_config.template

    template_info = get_full_template_info(template_config)
    template_params = template_info["params"]

    available_dependencies = []

    user = None if (not user_id) else get_user_model().objects.get(id=user_id)
    proposed_match = None if (not proposed_match_id) else ProposedMatch.objects.get(id=proposed_match_id)
    match = None if (not match_id) else Match.objects.get(id=match_id)
    
    print("user", user, "match", match, "proposed_match", proposed_match)

    if user:
        available_dependencies.append("user")

    if match:
        available_dependencies.append("match")
        
    if proposed_match:
        available_dependencies.append("proposed_match")

    for key in kwargs:
        available_dependencies.append(f"context.{key}")

    context = {}

    # 1 - check if all params are present & their dependenciencies are met
    for param in template_params:
        if param not in params:
            raise UnknownParameterException(f"Unknown parameter {param}")

        param_config = params[param]
        if not param_config.depends_on:
            continue

        if not set(param_config.depends_on).issubset(available_dependencies):
            raise MissingContextDependencyException(f"Missing context dependency for {param} in {available_dependencies} - {param_config.depends_on}")

        function_lookup = param_config.lookup
        function_lookup = function_lookup.split(".")
        module = importlib.import_module(".".join(function_lookup[:-1]))
        lookup_function = getattr(module, function_lookup[-1])

        lookup_context = {}
        for dependency in param_config.depends_on:
            param_name = param
            if dependency == "user":
                lookup_context["user"] = user
            elif dependency == "match":
                lookup_context["match"] = match
            elif dependency == "proposed_match":
                lookup_context["proposed_match"] = proposed_match
            elif dependency.startswith("context."):
                param_name = dependency.split(".")[1]
                print(kwargs)
                assert param_name in kwargs, f"Missing context dependency in **kwargs for {param}"
                if "context" not in lookup_context:
                    lookup_context["context"] = {}
                lookup_context["context"][param_name] = kwargs[param_name]

        # Perform the lookup injecting all dependencies
        context[param_name] = lookup_function(**lookup_context)
    return template_info, context


def render_template_dynamic_lookup(template_name, user_id=None, match_id=None, proposed_match_id=None, **kwargs):
    template_info, context = prepare_template_context(template_name, user_id, match_id, proposed_match_id, **kwargs)
    template_path = template_info["config"]["template"]

    return render_template_to_html(template_path, context)
