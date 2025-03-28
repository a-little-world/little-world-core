from django.urls import path
from django.shortcuts import redirect

from rest_framework.decorators import api_view
from rest_framework.response import Response
from management.models.user import User
from management.models.short_links import ShortLink, ShortLinkClick

@api_view(["GET"])
def short_link_click(request, tag):
    short_link = ShortLink.objects.get(tag=tag)
    # Only associate the user if they're authenticated
    source = request.query_params.get("source", "none")
    user_hash = request.query_params.get("user_hash", "none")
    if not request.user.is_authenticated:
        user = None
        if user_hash:
            qs_user = User.objects.filter(hash=user_hash)
            if qs_user.exists():
                user = qs_user.first()
    ShortLinkClick.objects.create(
        user=user, 
        short_link=short_link,
        source=source
    )
    return redirect(short_link.url)


api_urls = [
    path("links/<str:tag>/", short_link_click, name="short_link_click"),
]