from dataclasses import dataclass

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_dataclasses.serializers import DataclassSerializer

from management.models.question_deck import (
    QuestionCardCategories,
    QuestionCardsCategoriesSerializer,
    QuestionCardSerializer,
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

    if data.archive == True:
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
