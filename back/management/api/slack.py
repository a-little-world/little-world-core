from django.conf import settings
from django.urls import path, re_path
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from django.views.decorators.csrf import csrf_exempt
from rest_framework.response import Response
from openai import OpenAI
import os


def get_base_ai_client():
    if not settings.USE_AI:
        raise Exception("AI is not enabled!")
    if settings.AI_BASE_URL == "":
        return OpenAI(
            api_key=settings.AI_API_KEY,
        )
    else:
        return OpenAI(
            api_key=settings.AI_API_KEY,
            base_url=settings.AI_BASE_URL
        )


def notify_communication_channel(message):
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    

    SLACK_API_TOKEN = settings.SLACK_API_TOKEN
    CHANNEL_ID = settings.SLACK_REPORT_CHANNEL_ID

    bot_token = SLACK_API_TOKEN
    client = WebClient(token=bot_token)

    response = client.chat_postMessage(
        channel=CHANNEL_ID,
        mrkdwn=True,
        text=message,
        unfurl_links=False,
        unfurl_media=False
    )

def process_slack_ai_response(message):

    client = get_base_ai_client()    
    
    res = client.chat.completions.create(
        model=settings.AI_LANGUAGE_MODEL,
        messages=[{
            "role": "user",
            "content": message
        }],
    )
    
    response_message = res.choices[0].text
    notify_communication_channel(response_message)


@permission_classes([])
@authentication_classes([])
@api_view(['POST'])
def slack_callbacks(request, secret="false"):
    if secret != settings.SLACK_CALLBACK_SECRET:
        return Response("Invalid secret", status=403)
    if "challenge"  in request.data:
         return Response(request.data["challenge"])
    if request.data["event"]["type"] == "message":
        message = request.data["event"]["text"]
        if message.startswith("/ask "):
            message = message.replace("/ask ", "")
            
            process_slack_ai_response(message)

    return Response()
    
api_routes = [
    path("/api/slack/event_callbacks/<str:secret>/", csrf_exempt(slack_callbacks)),
] if settings.USE_SLACK_INTEGRATION else []