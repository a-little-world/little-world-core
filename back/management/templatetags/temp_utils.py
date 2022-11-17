from django import template
register = template.Library()


@register.simple_tag
def create_dict(str_dict):
    return eval(str_dict)
