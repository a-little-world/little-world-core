"""
Google Cloud Translation Client

This module provides a wrapper around the Google Cloud Translation API.
"""

from django.conf import settings
from google.cloud import translate_v2
from google.oauth2 import service_account


def get_google_translate_client() -> translate_v2.Client:
    """
    Initialize and return a Google Cloud Translation client.

    Returns:
        translate_v2.Client: Configured Google Cloud Translation client instance

    Raises:
        ValueError: If GOOGLE_CLOUD_CREDENTIALS is not configured in settings
    """
    credentials_data = getattr(settings, "GOOGLE_CLOUD_CREDENTIALS", None)

    if not credentials_data:
        raise ValueError("GOOGLE_CLOUD_CREDENTIALS is not configured in Django settings")

    credentials = service_account.Credentials.from_service_account_info(credentials_data)

    return translate_v2.Client(credentials=credentials)
