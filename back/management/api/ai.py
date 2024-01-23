from openai import OpenAI
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, authentication_classes
from management.models.state import State
from django.views import View
from django.urls import path, re_path
from django.contrib.auth.mixins import LoginRequiredMixin
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from management.tasks import request_streamed_ai_response
import time

availabol_model_configs = {
    "mixtral8x7B": {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "backend": "https://api.deepinfra.com/v1/openai/"
    },
    "gpt-4-turbo": {
        "model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
        "backend": "default"
    }
}


    
@api_view(['POST'])
@authentication_classes([SessionAuthentication])
def request_streamed_api_response(request):
    
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)
    
    
    mconf = request.data['model_config']
    if not mconf in availabol_model_configs:
        return Response({"error": f"Invalid model config, possible configs {', '.join(list(availabol_model_configs.keys()))}"}, status=400)
    
    model = availabol_model_configs[mconf]["model"]
    backend = availabol_model_configs[mconf]["backend"]
    
    task = request_streamed_ai_response.delay(request.data['messages'], model=model, backend=backend)
    
    return Response({
        "task_id" : task.task_id
        })


api_routes = [
    path("api/ai/prompt/", request_streamed_api_response),
] if settings.USE_AI else []