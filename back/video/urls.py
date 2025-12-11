from video.api import api_urls
from video.livekit_webhook import api_urls as livekit_webhook_api_urls
from video.random_call_management import api_urls as random_call_management_api_urls
from video.random_calls import api_urls as random_calls_api_urls

urlpatterns = [*api_urls, *random_calls_api_urls, *livekit_webhook_api_urls, *random_call_management_api_urls]
