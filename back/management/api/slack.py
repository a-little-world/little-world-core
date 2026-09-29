from django.conf import settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response


def get_base_ai_client():
    if not settings.USE_AI:
        raise Exception("AI is not enabled!")
    if settings.AI_BASE_URL == "":
        return OpenAI(
            api_key=settings.AI_API_KEY,
        )
    else:
        return OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL)


def notify_communication_channel(message):
    from slack_sdk import WebClient

    if not settings.USE_SLACK_INTEGRATION:
        return

    SLACK_API_TOKEN = settings.SLACK_API_TOKEN
    CHANNEL_ID = settings.SLACK_REPORT_CHANNEL_ID

    bot_token = SLACK_API_TOKEN
    client = WebClient(token=bot_token)

    client.chat_postMessage(channel=CHANNEL_ID, mrkdwn=True, text=message, unfurl_links=False, unfurl_media=False)


def notify_security_channel(message):
    from slack_sdk import WebClient

    if not settings.USE_SLACK_INTEGRATION:
        return

    SLACK_API_TOKEN = settings.SLACK_API_TOKEN
    CHANNEL_ID = settings.SLACK_SECURITY_REPORT_CHANNEL_ID
    if CHANNEL_ID == "":
        # TODO: raising causes development issues, raise in prod or just return?
        # raise Exception("SLACK_SECURITY_REPORT_CHANNEL_ID is not set, cannot notify security channel")
        return

    bot_token = SLACK_API_TOKEN
    client = WebClient(token=bot_token)

    client.chat_postMessage(channel=CHANNEL_ID, mrkdwn=True, text=message, unfurl_links=False, unfurl_media=False)


def _support_feedback_thread_registry() -> dict:
    """Resolve configured support-feedback Slack threads (named map + single default pair)."""
    threads = dict(getattr(settings, "SLACK_SUPPORT_FEEDBACK_THREADS", None) or {})
    channel_id = getattr(settings, "SLACK_SUPPORT_FEEDBACK_CHANNEL_ID", "") or ""
    thread_ts = getattr(settings, "SLACK_SUPPORT_FEEDBACK_THREAD_TS", "") or ""
    if channel_id and thread_ts and "default" not in threads:
        threads["default"] = {"channel_id": channel_id, "thread_ts": thread_ts, "label": "Support feedback"}
    return threads


def list_support_feedback_threads() -> list[dict]:
    """Return configured thread keys/labels (no secrets) for agents and the UI."""
    return [
        {"key": key, "label": (config or {}).get("label") or key}
        for key, config in _support_feedback_thread_registry().items()
    ]


def resolve_support_feedback_thread(thread_key: str | None = None) -> tuple[str, str]:
    """Return ``(channel_id, thread_ts)`` for a named thread or the default pair."""
    threads = _support_feedback_thread_registry()
    if thread_key:
        config = threads.get(thread_key)
        if config is None:
            raise ValueError(f"Unknown support feedback Slack thread: '{thread_key}'.")
        return config.get("channel_id") or "", config.get("thread_ts") or ""
    default = threads.get("default") or {}
    return default.get("channel_id") or "", default.get("thread_ts") or ""


def post_slack_thread_message(
    text: str,
    *,
    thread_key: str | None = None,
    channel_id: str | None = None,
    thread_ts: str | None = None,
):
    """Post ``text`` to a Slack channel/thread; no-op when Slack integration is disabled."""
    if not settings.USE_SLACK_INTEGRATION:
        return None
    if channel_id is None and thread_ts is None:
        channel_id, thread_ts = resolve_support_feedback_thread(thread_key)
    if not channel_id:
        raise ValueError("No Slack channel configured for support feedback.")
    from slack_sdk import WebClient

    client = WebClient(token=settings.SLACK_API_TOKEN)
    return client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts or None,
        mrkdwn=True,
        text=text,
        unfurl_links=False,
        unfurl_media=False,
    )


def post_support_feedback_to_slack(text: str, thread_key: str | None = None):
    """Thin wrapper used by the support_reply action's ``slack_feedback`` skill."""
    return post_slack_thread_message(text, thread_key=thread_key or None)


def process_slack_ai_response(message):
    client = get_base_ai_client()

    res = client.chat.completions.create(
        model=settings.AI_LANGUAGE_MODEL,
        messages=[{"role": "user", "content": message}],
    )

    response_message = res.choices[0].text
    notify_communication_channel(response_message)


@permission_classes([])
@authentication_classes([])
@api_view(["GET", "POST"])
def slack_callbacks(request, secret="false"):
    if secret != settings.SLACK_CALLBACK_SECRET:
        return Response("Invalid secret", status=403)
    if "challenge" in request.data:
        return Response(request.data["challenge"])
    if request.data["event"]["type"] == "message":
        message = request.data["event"]["text"]
        if message.startswith("/ask "):
            message = message.replace("/ask ", "")

            process_slack_ai_response(message)

    return Response()


# http://localhost:8000/api/slack/event_callbacks/test/
api_routes = (
    [
        path("api/slack/event_callbacks/<str:secret>/", csrf_exempt(slack_callbacks)),
    ]
    if settings.USE_SLACK_INTEGRATION
    else []
)
