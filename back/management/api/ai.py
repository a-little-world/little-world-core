from django.conf import settings
from rest_framework.decorators import api_view, authentication_classes
from management.models.state import State
from django.urls import path
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from management.tasks import request_streamed_ai_response

availabol_model_configs = {"mixtral8x7B": {"model": "mistralai/Mixtral-8x7B-Instruct-v0.1", "backend": settings.AI_BASE_URL}, "gpt-4-turbo": {"model": "gpt-4-1106-preview", "backend": "default"}, "gpt-4": {"model": "gpt-4", "backend": "default"}}


@api_view(["GET"])
def model_config_options(request):
    return Response(list(availabol_model_configs.keys()))


@api_view(["POST"])
@authentication_classes([SessionAuthentication])
def request_streamed_api_response(request):
    assert request.user.is_staff or request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER)

    mconf = request.data["model_config"]
    if mconf not in availabol_model_configs:
        return Response({"error": f"Invalid model config, possible configs {', '.join(list(availabol_model_configs.keys()))}"}, status=400)

    model = availabol_model_configs[mconf]["model"]
    backend = availabol_model_configs[mconf]["backend"]

    task = request_streamed_ai_response.delay(request.data["messages"], model=model, backend=backend)

    return Response({"task_id": task.task_id})


api_routes = (
    [
        path("api/ai/models/", model_config_options),
        path("api/ai/prompt/", request_streamed_api_response),
    ]
    if settings.USE_AI
    else []
)
