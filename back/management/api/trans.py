from rest_framework.views import APIView
from django.views.i18n import JavaScriptCatalog, JSONCatalog
from django.utils.translation.trans_real import DjangoTranslation
from django.utils.translation import get_language
from django.conf import settings
from rest_framework.response import Response
from rest_framework.decorators import api_view
from translations import get_translation_catalog

@api_view(['GET'])
def get_translation_catalogue(request, lang=None):
    
    catalog = get_translation_catalog()
    if lang:
        return Response(catalog[lang])

    return Response(catalog)