"""
Generic Translation API

This module provides a translation API that uses DeepL as the default translation service.
Supports both text translation and language listing.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from management.authentication import NativeOnlyJWTAuthentication
from management.clients import get_deepl_client


class TranslateTextSerializer(serializers.Serializer):
    """Serializer for translation requests"""
    target = serializers.CharField(required=True, help_text="Target language code (e.g., 'DE', 'FR', 'ES')")
    text = serializers.CharField(required=True, help_text="Text to translate")
    source = serializers.CharField(required=False, allow_null=True, allow_blank=True, help_text="Source language code (optional, auto-detected if not provided)")


@extend_schema(
    methods=["GET"],
    description="Get the list of supported languages for translation",
)
@api_view(["GET"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def languages(request):
    """
    Get the list of supported languages.
    
    Returns a list of language objects with their codes and names.
    """
    translator = get_deepl_client()
    
    # Get both source and target languages from DeepL
    source_languages = translator.get_source_languages()
    target_languages = translator.get_target_languages()
    
    # Format response to match the structure of the old Google Translate API
    languages_list = []
    
    # Use target languages as the main list (more comprehensive)
    for lang in target_languages:
        languages_list.append({
            "language": lang.code.lower(),  # DeepL uses uppercase, convert to lowercase for consistency
            "name": lang.name,
            "supports_formality": getattr(lang, "supports_formality", False),
        })
    
    return Response(languages_list)


@extend_schema(
    methods=["POST"],
    request=TranslateTextSerializer(many=False),
    description="Translate text to a target language using DeepL",
)
@api_view(["POST"])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
@permission_classes([IsAuthenticated])
def translate(request):
    """
    Translate text to a given target language.
    
    Request body:
        - text (str): The text to translate
        - target (str): Target language code (e.g., 'DE', 'FR', 'ES')
        - source (str, optional): Source language code (auto-detected if not provided)
    
    Returns:
        Translated text with metadata including detected source language
    """
    serializer = TranslateTextSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    target = serializer.validated_data["target"]
    text = serializer.validated_data["text"]
    source = serializer.validated_data.get("source")

    translator = get_deepl_client()

    # Handle bytes input
    if isinstance(text, bytes):
        text = text.decode("utf-8")

    result = translator.translate_text(
        text,
        target_lang=target,
        source_lang=source,  # None if not provided, DeepL will auto-detect
    )

    response_data = {
        "translatedText": result.text,
        "detectedSourceLanguage": result.detected_source_lang,
        "input": text,
    }

    return Response(response_data)

