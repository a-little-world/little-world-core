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
from management.models.question_deck import (
    QuestionCard,
    QuestionCardCategories,
    QuestionCardsCategoriesSerializer,
    QuestionCardsDeck,
    QuestionCardSerializer,
    _base_translations_dict,
)


@dataclass
class GetQuestionCards:
    category: str = "all"
    archived: bool = False
    items_per_page: int = 50
    page = 1


class GetQuestionCardsSerializer(DataclassSerializer):
    class Meta:
        dataclass = GetQuestionCards


@dataclass
class ArchiveCard:
    uuid: str
    archive: bool = False


class ArchiveCardSeralizer(DataclassSerializer):
    class Meta:
        dataclass = ArchiveCard


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@extend_schema(methods=["POST"], request=GetQuestionCardsSerializer(many=False))
def archive_card(request):
    serializer = ArchiveCardSeralizer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    user = request.user

    if data.archive:
        card = user.state.question_card_deck.cards.get(uuid=data.uuid)
        user.state.question_card_deck.archive_card(card)
    else:
        card = user.state.question_card_deck.cards_archived.get(uuid=data.uuid)
        user.state.question_card_deck.unarchive_card(card)

    return Response({})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@extend_schema(methods=["GET"], request=GetQuestionCardsSerializer(many=False))
def get_question_cards(request):
    serializer = GetQuestionCardsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()

    user = request.user

    all_categories = QuestionCardCategories.objects.all()

    resp = {"categories": QuestionCardsCategoriesSerializer(all_categories, many=True).data, "cards": {}}

    archived_category = {"uuid": "archived", "content": {"de": "Archiviert", "en": "Archived"}, "ref_id": 0}

    if data.category == "all":
        for category in all_categories:
            cards = user.state.question_card_deck.cards.filter(category=category)
            resp["cards"][str(category.uuid)] = QuestionCardSerializer(cards, many=True).data

        if data.archived:
            cards = user.state.question_card_deck.cards_archived.all()
            resp["cards"]["archived"] = QuestionCardSerializer(cards, many=True).data

            resp["categories"].append(archived_category)
    else:
        raise serializers.ValidationError("Not implemented")

    return Response(resp)


def _next_ref_id(model):
    max_ref_id = model.objects.order_by("-ref_id").values_list("ref_id", flat=True).first()
    return (max_ref_id or 0) + 1


def _normalize_content(content):
    if not isinstance(content, dict):
        raise serializers.ValidationError("Content must be an object with en and de keys.")
    return _base_translations_dict(en=content.get("en", ""), de=content.get("de", ""))


def _serialize_admin_category(category):
    cards = QuestionCard.objects.filter(category=category).order_by("ref_id")
    return {
        "uuid": str(category.uuid),
        "ref_id": category.ref_id,
        "content": category.content,
        "cards": [
            {
                "uuid": str(card.uuid),
                "ref_id": card.ref_id,
                "content": card.content,
            }
            for card in cards
        ],
    }


def _add_card_to_all_decks(card):
    for deck in QuestionCardsDeck.objects.all():
        deck.cards.add(card)


def _remove_card_from_all_decks(card):
    for deck in QuestionCardsDeck.objects.all():
        deck.cards.remove(card)
        deck.cards_archived.remove(card)


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


@api_view(["GET", "PUT"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_cards(request):
    if request.method == "GET":
        categories = QuestionCardCategories.objects.all().order_by("ref_id")
        return Response(
            {
                "categories": [_serialize_admin_category(category) for category in categories],
            }
        )

    serializer = AdminQuestionCardsWriteSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    with transaction.atomic():
        saved_categories = []
        for category_data in serializer.validated_data["categories"]:
            category_uuid = category_data.get("uuid")
            content = category_data["content"]
            cards_data = category_data.get("cards", [])

            if category_uuid:
                category = get_object_or_404(QuestionCardCategories, uuid=category_uuid)
                category.content = content
                category.save(update_fields=["content"])
            else:
                category = QuestionCardCategories.objects.create(
                    ref_id=_next_ref_id(QuestionCardCategories),
                    content=content,
                )

            saved_cards = []
            for card_data in cards_data:
                card_uuid = card_data.get("uuid")
                card_content = card_data["content"]

                if card_uuid:
                    card = get_object_or_404(QuestionCard, uuid=card_uuid, category=category)
                    card.content = card_content
                    card.save(update_fields=["content"])
                else:
                    card = QuestionCard.objects.create(
                        category=category,
                        ref_id=_next_ref_id(QuestionCard),
                        content=card_content,
                    )
                    _add_card_to_all_decks(card)

                saved_cards.append(
                    {
                        "uuid": str(card.uuid),
                        "ref_id": card.ref_id,
                        "content": card.content,
                    }
                )

            saved_categories.append(
                {
                    "uuid": str(category.uuid),
                    "ref_id": category.ref_id,
                    "content": category.content,
                    "cards": saved_cards,
                }
            )

    return Response({"categories": saved_categories})


@api_view(["DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_card_category_detail(request, category_uuid):
    category = get_object_or_404(QuestionCardCategories, uuid=category_uuid)
    with transaction.atomic():
        for card in QuestionCard.objects.filter(category=category):
            _remove_card_from_all_decks(card)
        category.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["DELETE"])
@permission_classes([IsAdminOrMatchingUser])
@authentication_classes([SessionAuthentication, NativeOnlyJWTAuthentication])
def admin_question_card_detail(request, card_uuid):
    card = get_object_or_404(QuestionCard, uuid=card_uuid)
    with transaction.atomic():
        _remove_card_from_all_decks(card)
        card.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
