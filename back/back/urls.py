from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static


"""
We are adding all app urls under `'/'` their paths should be set under `<app>/urls.py`
Admin paths registered last
"""

urlpatterns = [
    path('', include('management.urls')),
    path('admin/', admin.site.urls),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
