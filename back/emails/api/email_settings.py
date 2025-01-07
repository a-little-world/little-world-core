from django.urls import path

from rest_framework.response import Response
from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)

from management.models.settings import EmailSettings

from emails.api.emails_config import EMAILS_CONFIG


def get_unsubscribed_categories():
    unsubscribale_categories = [category for category in EMAILS_CONFIG.categories if EMAILS_CONFIG.categories[category].unsubscribe]
    return unsubscribale_categories


@api_view(["GET"])
@permission_classes([])
@authentication_classes([])
def retrieve_email_settings(request, email_settings_hash):
    settings = EmailSettings.objects.filter(hash=email_settings_hash)
    if not settings.exists():
        return Response({"detail": "Not found"}, status=404)

    settings = settings.first()

    unsubscribale_categories = get_unsubscribed_categories()
    subscribed_categories = [category for category in unsubscribale_categories if (category not in settings.unsubscribed_categories)]

    return Response(
        {
            "categories": unsubscribale_categories,
            "unsubscribed_categories": settings.unsubscribed_categories,
            "subscribed_categories": subscribed_categories,
        }
    )


def toggle_category_subscribe(request, email_settings_hash, category, subscribed=False):
    settings = EmailSettings.objects.filter(hash=email_settings_hash)
    if not settings.exists():
        return Response({"detail": "Not found"}, status=404)

    settings = settings.first()

    unsubscribale_categories = get_unsubscribed_categories()
    if category not in unsubscribale_categories:
        return Response({"detail": "Invalid category"}, status=400)

    if not subscribed:
        # Unsubscribe
        if category in settings.unsubscribed_categories:
            return Response({"detail": "Already unsubscribed"}, status=400)
        else:
            settings.unsubscribed_categories.append(category)
            settings.save()
            return Response({"detail": f"Un-Subscribed '{category}'"})
    else:
        # Subscribe
        if category not in settings.unsubscribed_categories:
            return Response({"detail": "Already subscribed"}, status=400)
        else:
            settings.unsubscribed_categories.remove(category)
            settings.save()
            return Response({"detail": f"Subscribed '{category}'"})


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def unscubscribe_category(request, email_settings_hash, category):
    return toggle_category_subscribe(request, email_settings_hash, category, subscribed=False)


@api_view(["POST"])
@permission_classes([])
@authentication_classes([])
def subscribe_category(request, email_settings_hash, category):
    return toggle_category_subscribe(request, email_settings_hash, category, subscribed=True)


api_urls = [
    path(
        "api/email_settings/<str:email_settings_hash>/<str:category>/subscribe",
        subscribe_category,
    ),
    path(
        "api/email_settings/<str:email_settings_hash>/<str:category>/unsubscribe",
        unscubscribe_category,
    ),
    path("api/email_settings/<str:email_settings_hash>/", retrieve_email_settings),
]
