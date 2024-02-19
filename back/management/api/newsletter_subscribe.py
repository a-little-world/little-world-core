from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from management.models.newsletter import NewsLetterSubscription, NewsletterSubscriptionSerializer
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema


class NewsletterSubscriptionParamsSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

@extend_schema(
    request=NewsletterSubscriptionParamsSerializer,
)
@api_view(['POST'])
@permission_classes([AllowAny])
def public_newsletter_subscribe(request):
    serializer = NewsletterSubscriptionParamsSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    
    email = serializer.data['email']
    
    if NewsLetterSubscription.objects.filter(email=email).exists():
        pass
    else:
        NewsLetterSubscription.objects.create(email=email)

    # No information leakage!
    return Response("OK", status=status.HTTP_200_OK)