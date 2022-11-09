"""
This are all the outsources schema extensions to make all the open api magic work
they heavily rely on information the basic model APIViews offer, this suffices for all basic actions
but you can also extend them how ever you want
"""
from . import register
from drf_spectacular.utils import OpenApiParameter, OpenApiExample

registration = dict(
    # extra parameters added to the schema
    parameters=[
        OpenApiParameter(
            name=param, description=f'{param} for Registration',
            required=True, type=str)
        for param in register.Register.required_args
    ],
    description='Little World Registration API called with data from the registration form',
    auth=None,
    operation_id=None,
    operation=None,
    methods=["POST"],
    request=register.RegistrationSerializer(many=False)
)
