# This little hack here allowes me to use full syntax hightlighting and type checking without having the django project setup up
# Pylint doesn't globaly know the django apps, but it does recognize ./back as a package
# So when we prefix the import with back.--inport-- we get all the syntax suggar :)
import random
from back.management import random_test_users  # !dont_include
from back.management.models import State  # !dont_include
# !include from management.models import State
# !include from management import random_test_users

random_test_users.create_abunch_of_users(19)

devuser = random_test_users.create_test_user(
    20, password="Test321!", email="devuser@mail.com")

print(devuser, devuser.state, devuser.state.extra_user_permissions)

# Setup default permissions for auto-login and viewing docs:
devuser.state.auto_login_api_token = "devUserAutoLoginTokenXYZ"
devuser.state.extra_user_permissions = []
devuser.state.extra_user_permissions.append(
    State.ExtraUserPermissionChoices.AUTO_LOGIN)
devuser.state.extra_user_permissions.append(
    State.ExtraUserPermissionChoices.DOCS_VIEW)
devuser.state.extra_user_permissions.append(
    State.ExtraUserPermissionChoices.API_SCHEMAS)
devuser.state.extra_user_permissions.append(
    State.ExtraUserPermissionChoices.DATABASE_SCHEMA)
devuser.state.save()
