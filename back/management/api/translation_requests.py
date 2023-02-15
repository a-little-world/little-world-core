from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from rest_framework.response import Response
from googletrans import Translator
from rest_framework import serializers, status
from drf_spectacular.utils import extend_schema
from management.models import TranslationLog


class TranslationRequestSerializer(serializers.Serializer):
    text = serializers.CharField(required=True)
    source_lang = serializers.CharField(required=True)
    target_lang = serializers.CharField(required=True)

    def create(self, validated_data):
        return validated_data


@extend_schema(request=TranslationRequestSerializer(many=False))
@login_required
@api_view(['POST'])
def translate(request):

    serializer = TranslationRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    params = serializer.save()

    translator = Translator()

    tranlation = translator.translate(
        params['text'], src=params['source_lang'], dest=params['target_lang'])

    TranslationLog.objects.create(
        user=request.user,
        source_lang=params['source_lang'],
        dest_lang=params['target_lang'],
        text=params['text'],
        translation=tranlation.text
    )

    return Response({"trans": tranlation.text}, status=status.HTTP_200_OK)
