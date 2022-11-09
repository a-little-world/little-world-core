"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""
from .models import User
from django.conf import settings
from .models import UserSerializer


def get_user(user, lookup="email"):
    """
    Three ways to look up a user: email, hash or pk
    pk is obviously the fastest, but generaly we shouldn't have to care
    we could also add some neat indexing here to speed up further
    """
    if lookup == "email":
        return get_user_by_email(user)
    elif lookup == "hash":
        return get_user_by_hash(user)
    elif lookup == "pk":
        return get_user_by_pk(user)
    else:
        raise Exception(f"lookup '{lookup}' doesn't exist ")


def get_user_by_email(email):
    return User.objects.get(email=email)


def get_user_by_hash(hash):
    # TODO: here i'm assuming that .get return only one object and throws an error if there are multiple
    return User.objects.get(hash=hash)


# We accept string input, but this will error if its not convertable to int
def get_user_by_pk(pk):
    pk = int(pk)
    # we use .get with primary key so we will always get only one user
    return User.objects.get(id=pk)


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

    # Step 2 ... TODO


def match_users(users: set):
    """ Accepts a list of two users to match """
    assert len(users) == 2, "Accepts only two users!"
    # Match ... TODO


def unmatch_users(users: set):
    """ Accepts a list of two users to unmatch """
    assert len(users) == 2, "Accepts only two users!"
    # Un-Match ... TODO


def get_base_management_user():
    """
    Always returns the BASE_MANAGEMENT_USER user
    """
    get_user_by_email(settings.BASE_MANAGEMENT_USER_EMAIL)


# TODO: can this cause issues when settings not initalized?
def send_chat_message(to_user, from_user, message):
    """
    This can send a chat message from any user to any user
    this is intended to the used by the BASE_MANAGEMENT_USER
    so usualy the from_user would be 'get_base_management_user'
    """
    # Send a chat message ... TODO
