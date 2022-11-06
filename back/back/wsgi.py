"""
WSGI config for back project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/howto/deployment/wsgi/
"""

from whitenoise import WhiteNoise
import os
from django.conf import settings
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'back.settings')

application = get_wsgi_application()

if settings.BUILD_TYPE in ['development', 'staging']:
    root_path = settings.STATIC_ROOT
    application = WhiteNoise(application, root=root_path)
