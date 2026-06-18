from dataclasses import dataclass

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from management.authentication import NativeOnlyJWTAuthentication
from management.helpers import IsAdminOrMatchingUser
from management.models.question_cards import (
    QuestionCard,
    QuestionCardCategory,
    UserQuestionCardPreference,
    default_translation_content,
)

ARCHIVED_CATEGORY = {
    "uuid": "archived",
    "content": {"de": "Archiviert", "en": "Archived"},
}


class QuestionCardCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionCardCategory
        fields = ["uuid", "content"]


class QuestionCardSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionCard
        fields = ["uuid", "content"]


@dataclass
class GetQuestionCards:
    category: str = "all"
    archived: bool = False


class GetQuestionCardsSerializer(DataclassSerializer):
    class Meta:
        dataclass = GetQuestionCards


@dataclass
class ArchiveCard:
    uuid: str
    archive: bool = False


class ArchiveCardSerializer(DataclassSerializer):
    class Meta:
        dataclass = ArchiveCard


def _normalize_content(content):
    if not isinstance(content, dict):
        raise serializers.ValidationError("Content must be an object with en and de keys.")
    return default_translation_content(en=content.get("en", ""), de=content.get("de", ""))


def _archived_card_ids_for_user(user):
    return UserQuestionCardPreference.objects.filter(
        user=user,
        kind=UserQuestionCardPreference.Kind.ARCHIVED,
    ).values_list("card_id", flat=True)


def _active_cards_queryset(*, category=None, exclude_card_ids=()):
    qs = QuestionCard.objects.filter(is_active=True).order_by("sort_order", "uuid")
    if category is not None:
        qs = qs.filter(category=category)
    if exclude_card_ids:
        qs = qs.exclude(pk__in=exclude_card_ids)
    return qs


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@extend_schema(methods=["POST"], request=ArchiveCardSerializer)
def archive_card(request):
    serializer = ArchiveCardSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    card = get_object_or_404(QuestionCard, uuid=data.uuid, is_active=True)

    if data.archive:
        UserQuestionCardPreference.objects.get_or_create(
            user=request.user,
            card=card,
            kind=UserQuestionCardPreference.Kind.ARCHIVED,
        )
    else:
        UserQuestionCardPreference.objects.filter(
            user=request.user,
            card=card,
            kind=UserQuestionCardPreference.Kind.ARCHIVED,
        ).delete()

    return Response({})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@extend_schema(methods=["GET"], request=GetQuestionCardsSerializer)
def get_question_cards(request):
    serializer = GetQuestionCardsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    if data.category != "all":
        raise serializers.ValidationError({"category": "Only 'all' is supported."})

    user = request.user
    archived_ids = list(_archived_card_ids_for_user(user))
    categories = QuestionCardCategory.objects.all().order_by("sort_order", "uuid")

    resp = {
        "categories": QuestionCardCategorySerializer(categories, many=True).data,
        "cards": {
            str(category.uuid): QuestionCardSerializer(
                _active_cards_queryset(category=category, exclude_card_ids=archived_ids),
                many=True,
            ).data
            for category in categories
        },
    }

    if data.archived:
        archived_cards = QuestionCard.objects.filter(
            is_active=True,
            pk__in=archived_ids,
        ).order_by("sort_order", "uuid")
        resp["cards"]["archived"] = QuestionCardSerializer(archived_cards, many=True).data
        resp["categories"] = [*resp["categories"], ARCHIVED_CATEGORY]

    return Response(resp)


class AdminQuestionCardWriteSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=False, allow_null=True)
    content = serializers.JSONField()

    def validate_content(self, value):
        return _normalize_content(value)


class AdminQuestionCategoryWriteSerializer(serializers.Serializer):
    uuid = serializers.UUIDField(required=False, allow_null=True)
    content = serializers.JSONField()
    cards = AdminQuestionCardWriteSerializer(many=True, required=False, default=list)

    def validate_content(self, value):
        return _normalize_content(value)


class AdminQuestionCardsWriteSerializer(serializers.Serializer):
    categories = AdminQuestionCategoryWriteSerializer(many=True)


def _serialize_admin_category(category):
    cards = category.cards.order_by("sort_order", "uuid")
    return {
        "uuid": str(category.uuid),
        "sort_order": category.sort_order,
        "content": category.content,
        "cards": [
            {
                "uuid": str(card.uuid),
                "sort_order": card.sort_order,
                "content": card.content,
            }
            for card in cards
        ],
    }


@api_view(["GET", "PUT"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_cards(request):
    if request.method == "GET":
        categories = QuestionCardCategory.objects.prefetch_related("cards").order_by("sort_order", "uuid")
        return Response({"categories": [_serialize_admin_category(category) for category in categories]})

    serializer = AdminQuestionCardsWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        saved_categories = []
        for category_index, category_data in enumerate(serializer.validated_data["categories"]):
            category_uuid = category_data.get("uuid")
            content = category_data["content"]
            cards_data = category_data.get("cards", [])

            if category_uuid:
                category = get_object_or_404(QuestionCardCategory, uuid=category_uuid)
                category.content = content
                category.sort_order = category_index
                category.save(update_fields=["content", "sort_order"])
            else:
                category = QuestionCardCategory.objects.create(
                    content=content,
                    sort_order=category_index,
                )

            saved_cards = []
            for card_index, card_data in enumerate(cards_data):
                card_uuid = card_data.get("uuid")
                card_content = card_data["content"]

                if card_uuid:
                    card = get_object_or_404(QuestionCard, uuid=card_uuid, category=category)
                    card.content = card_content
                    card.sort_order = card_index
                    card.save(update_fields=["content", "sort_order"])
                else:
                    card = QuestionCard.objects.create(
                        category=category,
                        content=card_content,
                        sort_order=card_index,
                    )

                saved_cards.append(
                    {
                        "uuid": str(card.uuid),
                        "sort_order": card.sort_order,
                        "content": card.content,
                    }
                )

            saved_categories.append(
                {
                    "uuid": str(category.uuid),
                    "sort_order": category.sort_order,
                    "content": category.content,
                    "cards": saved_cards,
                }
            )

    return Response({"categories": saved_categories})


@api_view(["DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_card_category_detail(request, category_uuid):
    category = get_object_or_404(QuestionCardCategory, uuid=category_uuid)
    if category.cards.exists():
        return Response(
            {"detail": "Remove all cards from this category before deleting it."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    category.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_card_detail(request, card_uuid):
    card = get_object_or_404(QuestionCard, uuid=card_uuid)
    card.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
