"""
This is a controller for any userform related actions
e.g.: Creating a new user, sending a notification to a users etc...
"""
from .models import User
from django.conf import settings
from .models import UserSerializer, User, Profile, State
from django.utils.translation import gettext as _


class UserNotFoundErr(Exception):
    pass


# All models *every* user should have!
user_models = {  # Model, primary key name
    "user": [User, 'email'],
    "profile": [Profile, 'user'],
    "state": [State, 'user']
}


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


def __user_get_catch(**kwargs):
    try:
        return User.objects.get(**kwargs)
    except User.DoesNotExist as e:
        # We should throw an error if a user was looked up that doesn't exist
        # If this error occurs we most likely forgot to delte the user from someones matches
        # But we still allow this to be caught with 'try' and returned as a parsed error
        raise UserNotFoundErr(_("User doesn't exist"))


def get_user_by_email(email):
    return __user_get_catch(email=email)


def get_user_by_hash(hash):
    # TODO: here i'm assuming that .get return only one object and throws an error if there are multiple
    return __user_get_catch(hash=hash)


# We accept string input, but this will error if its not convertable to int
def get_user_by_pk(pk):
    pk = int(pk)
    # we use .get with primary key so we will always get only one user
    return __user_get_catch(id=pk)


def get_user_models(user):
    # We don't need to catch any user not found erros,
    # cause you need to first get the usr and that should be done with get_user_*
    d = {}
    for k in user_models:
        elem = user_models[k][0].objects.get(
            user=user) if k != "user" else user
        d[k] = elem
    return d


def create_user(
    email,
    password,
    first_name,
    second_name,
    birth_year,
    send_verification_mail=True
):
    """ 
    This should be used when creating a new user, it may throw validations errors!
    performs the following setps:
    Note: this assumes some rought validations steps where done already, see `api.register.Register`
    1 - validate for user model
    2 - validate for profile model
    3 - create all models <- happens automaticly when the user model is created, see management.models.user.UserManager
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

    # If you don't want this to error catch serializers.ValidationError!
    user_data_serializer.is_valid(raise_exception=True)
    # The user_data_serializer automaticly creates the user model
    # The User model automaticly creates Profile, State, Settings, see models.user.UserManager
    user = user_data_serializer.save()

    # Step 2 ... TODO send mail


def match_users(users: set):  # 'set' No one can put two identical users
    """ Accepts a list of two users to match """
    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
    # Match ... TODO


def unmatch_users(users: set):
    """ Accepts a list of two users to unmatch """
    assert len(users) == 2, f"Accepts only two users! ({', '.join(users)})"
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
    pass
