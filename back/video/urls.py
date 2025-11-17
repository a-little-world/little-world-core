from video.api import api_urls
from video.random_calls import api_urls as random_calls_api_urls

urlpatterns = [*api_urls, *random_calls_api_urls]
