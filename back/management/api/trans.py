from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import SessionAuthentication
from rest_framework.response import Response
from translations import get_translation_catalog


@api_view(["GET"])
def get_translation_catalogue(request, lang=None):
    catalog = get_translation_catalog()
    if lang:
        return Response(catalog[lang])

    return Response(catalog)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([SessionAuthentication])
def api_translations(request):
    from translations import get_translation_catalog
    return Response(get_translation_catalog())
