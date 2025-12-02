"""
DeepL Translation Client

This module provides a wrapper around the DeepL Python library for translation services.
Documentation: https://github.com/deeplcom/deepl-python
"""

import deepl
from django.conf import settings


def get_deepl_client() -> deepl.Translator:
    """
    Initialize and return a DeepL Translator client.

    Returns:
        deepl.Translator: Configured DeepL translator instance

    Raises:
        ValueError: If DEEPL_API_KEY is not configured in settings
    """
    api_key = getattr(settings, "DEEPL_API_KEY", None)

    if not api_key:
        raise ValueError("DEEPL_API_KEY is not configured in Django settings")

    # Initialize the DeepL translator with the API key
    translator = deepl.Translator(api_key)

    return translator
