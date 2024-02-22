from django.template.loader import render_to_string
from django.http import HttpResponse
from django.urls import path

def get_reload_script(request):
    code = render_to_string("reload-script.js", {})
    return HttpResponse(code, content_type="application/javascript", charset='utf-8')

urlpatters = [
    path('api/auto-reload/reload-script.js', get_reload_script)
]