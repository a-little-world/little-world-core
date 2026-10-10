import re

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt

# YouTube video ids are always 11 chars (letters, digits, _ and -).
VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")


# The native app renders its web bundle from a local file:// page, which has no
# origin and sends no Referer. YouTube blocks embedded players without a Referer
# (error 153), so native embeds load this page from the app's https origin and
# the browser then provides the Referer when it loads the YouTube iframe.
@xframe_options_exempt
def youtube_embed(request):
    video_id = request.GET.get("v", "")
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        return HttpResponse("Missing or invalid video id (?v=VIDEO_ID)", status=400)

    return render(
        request,
        "youtube_embed.html",
        {"video_id": video_id, "title": request.GET.get("title", "")[:200]},
    )
