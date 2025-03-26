from django.urls import path
from django.shortcuts import redirect

from rest_framework.decorators import api_view
from rest_framework.response import Response
from management.models.short_links import ShortLink, ShortLinkClick

@api_view(["GET"])
def short_link_click(request, tag):
    short_link = ShortLink.objects.get(tag=tag)
    # Only associate the user if they're authenticated
    user = request.user if request.user.is_authenticated else None
    ShortLinkClick.objects.create(user=user, short_link=short_link)
    return redirect(short_link.url)


api_urls = [
    path("links/<str:tag>/", short_link_click, name="short_link_click"),
]