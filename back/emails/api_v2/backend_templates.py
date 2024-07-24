import json
from management.views.matching_panel import IsAdminOrMatchingUser
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from management.models.state import State
from django.shortcuts import render
from django.urls import path
from rest_framework.response import Response
from django.http import HttpResponse
from django.template import Template, Context
from django.template.loader import get_template
from django.template.base import VariableNode, NodeList, Parser
from emails.api_v2.emails_config import EMAILS_CONFIG


@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def email_config(request):
    # TODO: secure
    return Response(EMAILS_CONFIG)

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def render_backend_template(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)
    
    if not template_config:
        return Response({"error": "Template not found"}, status=404)
    
    template = template_config.template
    
    return render(request, template)

def extract_variables_from_template(template_name):
    template = get_template(template_name)
    
    def extract_from_nodes(nodelist):
        variables = set()
        for node in nodelist:
            if isinstance(node, VariableNode):
                variables.update(token.strip() for token in node.filter_expression.token.split('|')[0].split('.'))
            elif hasattr(node, 'nodelist'):
                variables.update(extract_from_nodes(node.nodelist))
            elif isinstance(node, NodeList):
                variables.update(extract_from_nodes(node))
        return variables

    variables = extract_from_nodes(template.template.nodelist)

    return variables

def get_full_template_info(template_config):
    variables = extract_variables_from_template(template_config.template)

    return {
        "config": template_config.to_dict(),
        "params": list(variables),
        "view": "/matching/emails/templates/" + template_config.id + "/"
    }

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def show_template_info(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)
    
    if not template_config:
        return Response({"error": "Template not found"}, status=404)
    
    return Response(get_full_template_info(template_config))

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def list_templates(request):

    templates = []
    for template_name in EMAILS_CONFIG.emails:

        template_config = EMAILS_CONFIG.emails.get(template_name)
        templates.append(get_full_template_info(template_config))

    return Response(templates)
    

api_urls = [
    path('matching/emails/config/', email_config),
    path('matching/emails/templates/', list_templates),
    path('matching/emails/templates/<str:template_name>/', render_backend_template),
    path('matching/emails/templates/<str:template_name>/info/', show_template_info),
]