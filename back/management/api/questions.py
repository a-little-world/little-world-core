from django.shortcuts import render
# Create your views here.
from management.models.question_deck import CardContent, UserDeck
from management.models.user import User
from rest_framework.response import Response
from rest_framework.decorators import APIView
from rest_framework import serializers
from rest_framework import status, permissions
from drf_spectacular.utils import extend_schema
from management.models.state import State
from collections import OrderedDict
from django.core.exceptions import ObjectDoesNotExist



# Serializer for CardContent model
class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = CardContent
        fields = '__all__'


# Serializer for UserDeck model
class UserCategorySerializer(serializers.ModelSerializer):
    user_deck = serializers.SerializerMethodField("get_categories")

    def get_categories(self, obj):
        categories_data = CategorySerializer(obj.content_id.all(), many=True).data

        # Create a dictionary to store the formatted data
        return categories_data

    class Meta:
        model = UserDeck
        fields = '__all__'
        extra_fields = ['category']



class RequestSerializer(serializers.Serializer):
    card_id = serializers.IntegerField()


class QuestionApi(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="This api view is used to show all unarchived questions"
    )

    def get(self, request):

        try:
            # Fetch the UserCategories object for the specific user
            user_categories = UserDeck.objects.get(user=request.user)
            
            # Serialize the UserCategories object using the UserCategorySerializer
            serializer = UserCategorySerializer(user_categories) 

            category = CardContent.objects.all().values_list("category_name", flat=True)
            list_of_dicts = list(OrderedDict((tuple(cat_obj.items()), cat_obj) for cat_obj in category).values())
            result = {'data':serializer.data["user_deck"],'category':list_of_dicts}

            return Response({"code": 200, "data": result}, status=status.HTTP_200_OK)
        
        except ObjectDoesNotExist:
            return Response({"code": 404, "error": "UserCategories not found"}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            return Response({"code": 500, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class ArchivedQuestionsApi(APIView):
    """
    This method is used to archive a question from a particular user's categories.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="This api view is used to archived the questions",
        methods=["POST"],
        request=RequestSerializer,  # Use the request serializer
    )

    def post(self, request):
        # checking for data

        if request.data:
            serializer = RequestSerializer(data=request.data)
        else:
            return Response({"code": 404, "error": "Category id not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # checking for serializer validation

        if serializer.is_valid():
            card_id = serializer.validated_data['card_id']

            try:
                # get an object for for user categories
                user_categories = UserDeck.objects.get(user=request.user)

                # remove User user_deck archived values
                category = CardContent.objects.get(id=card_id)

                # check if category exist
                if category in user_categories.content_id.all():
                    user_categories.content_id.remove(category)

                    # remove state user_deck archived values
                    state_user_deck = State.objects.get(user=request.user)
                    state_user_deck.user_deck.remove(category)
                    return Response({"code": 204, "msg": "Category removed successfully"}, status=status.HTTP_204_NO_CONTENT)
                else:
                    return Response({"code": 404, "msg": "Category Not Found"}, status=status.HTTP_404_NOT_FOUND)
            
            except UserDeck.DoesNotExist:
                return Response({"code": 404, "error": "UserCategories not found"}, status=status.HTTP_404_NOT_FOUND)
            
            except CardContent.DoesNotExist:
                return Response({"code": 404, "error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
            
            except Exception as e:
                return Response({"code": 500, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        else:
            return Response(serializer.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ViewArchivedList(APIView):
    """
    GET all archived cards
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="This api view is used to show all archived questions"
    )

    def get(self, request):

        try:
            # Fetch the first user's user deck
            user_deck = UserDeck.objects.get(user=request.user)
            
            # Get the content IDs associated with the user
            user_content_ids = user_deck.content_id.all()
            
            # Retrieve all available CardContent objects
            all_content = CardContent.objects.all()
            
            # Find the CardContent objects that are not associated with the user
            archived_content = all_content.difference(user_content_ids)
            
            # Serialize the results
            serializer = CategorySerializer(archived_content, many=True)
            
            # Return the serialized data
            return Response({"code": 200, "data": serializer.data}, status=status.HTTP_200_OK)
        
        except UserDeck.DoesNotExist:
            return Response({"code": 404, "error": "UserDeck not found"}, status=status.HTTP_404_NOT_FOUND)
        
        except Exception as e:
            return Response({"code": 500, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UnArchivedCard(APIView):
    """
    This Api used to Unarchive cards
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        description="This api view is used to unarchived the questions",
        methods=["POST"],
        request=RequestSerializer,  # Use the request serializer
    )

    def post(self, request):

        if request.data:
            serializer = RequestSerializer(data=request.data)
        else:
            return Response({"code": 404, "error": "Category id not found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Checking for serializer validation
        if serializer.is_valid():
            card_id = serializer.validated_data['card_id']

            try:
                # Retrieve the user's categories
                user_content = UserDeck.objects.get(user=request.user)

                # Fetch the category by its ID
                content = CardContent.objects.get(id=card_id)

                if content not in user_content.content_id.all():
                    # Add the category to the user's content
                    user_content.content_id.add(content)
                else:
                    return Response({"code": 400, "msg": "Content Already Exist"}, status=status.HTTP_400_BAD_REQUEST)

                # Return a success response
                return Response({"code": 200, "data": "Added Successfully"}, status=status.HTTP_200_OK)

            except UserDeck.DoesNotExist:
                return Response({"code": 404, "error": "UserDeck not found"}, status=status.HTTP_404_NOT_FOUND)
            
            except CardContent.DoesNotExist:
                return Response({"code": 404, "error": "Category not found"}, status=status.HTTP_404_NOT_FOUND)
            
            except Exception as e:
                return Response({"code": 500, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response(serializer.errors, status=status.HTTP_500_INTERNAL_SERVER_ERROR)