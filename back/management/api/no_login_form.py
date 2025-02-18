"""
This represents a class of forms that dont require the user to login
Every form has a unique hash that is always cuppled to a unique user
That way we can allow to render and updated the form without the user having to log-in
"""

from dataclasses import dataclass
from typing import Literal

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework_dataclasses.serializers import DataclassSerializer


@dataclass
class NoLoginFormData:
    form_hash: str
    ford_data: dict


@dataclass
class StillInContactFormData:
    still_in_contact: bool
    contact_duration: Literal["1week", "2weeks", "3weeks"]


class StillInContactFormDataSerializer(DataclassSerializer):
    class Meta:
        dataclass = StillInContactFormData


class NoLoginFormDataSerializer(DataclassSerializer):
    class Meta:
        dataclass = NoLoginFormData


@extend_schema(
    request=NoLoginFormDataSerializer(many=False),
)
@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def no_login_form(request):
    """
    This api required no authentication but can still link submitted for data to a user
    """
    from management.models.no_login_form import FORMS, NoLoginForm

    serializer = NoLoginFormDataSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    data = serializer.save()

    no_login_form = NoLoginForm.objects.get(hash=data.form_hash)

    # now we need to get or create the corresponding form model
    form_model = FORMS[no_login_form.form_type]["model"]
    model_object = form_model.objects.filter(form=no_login_form)

    if not model_object.exists():
        # then we have to first create that form model
        pass

    # TODO: finish this...

    pass
