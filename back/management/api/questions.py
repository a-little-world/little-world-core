from management.models.user import User
from rest_framework.response import Response
from rest_framework.decorators import APIView
from rest_framework import serializers
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema
from management.models.state import State
from collections import OrderedDict
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions
from management.models.question_deck import QuestionCard, QuestionCardCategories, QuestionCardsCategoriesSerializer, QuestionCardSerializer
from rest_framework_dataclasses.serializers import DataclassSerializer
from dataclasses import dataclass



@dataclass
class GetQuestionCards:
    category: str = "all"
    archived: bool = False
    items_per_page: int = 50
    page = 1
    

class GetQuestionCardsSerializer(DataclassSerializer):
    class Meta:
        dataclass = GetQuestionCards


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_question_cards(request):
    

    serializer = GetQuestionCardsSerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    data = serializer.save()
    
    user = request.user
    
    all_categories = QuestionCardCategories.objects.all()
    
    resp = {
        "categories": QuestionCardsCategoriesSerializer(all_categories, many=True).data,
        "cards" : {}
    }

    if data.category == "all":
        
        for category in all_categories:
            if data.archived:
                cards = user.state.question_card_deck.cards_archived.filter(category=category)
            else: 
                cards = user.state.question_card_deck.cards.filter(category=category)
            
            resp["cards"][str(category.uuid)] = QuestionCardSerializer(cards, many=True).data
    else:
        raise serializers.ValidationError("Not implemented")
    
    
    return Response(resp)
    


