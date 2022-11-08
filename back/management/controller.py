"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""
from .models import UserSerializer


def create_user(
    username,
    email,
    password,
    first_name,
    second_name,
    birth_year
):
    """ 
    This should be used when creating a new user, it may throw validations errors!
    performs the following setps:
    Note: this assumes some rought validations steps where done already, see `api.register.Register`
    1 - validate for user model
    2 - validate for profile model
    3 - create all models
    4 - send email verification code
    """
    # Step 1

    user_data_serializer = UserSerializer(data=dict(
        # Currently we don't allow any specific username
        username=email,
        email=email,
        first_name=first_name,
        second_name=second_name,
        password=password
    ))  # type: ignore
    user_data_serializer.is_valid(raise_exception=True)

    # Step 2
