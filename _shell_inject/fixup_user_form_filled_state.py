# To be run after the default fixture import
# We need to add all users to the matches of the default admin user
import json
from back.management import controller  # !dont_include
from back.management.models import User  # !dont_include
from back.management.models import rooms  # !dont_include
# !include from management.models import rooms
# !include from management import controller
# !include from management.models import User

with open("transformed_fixture.json") as f:
    data = json.loads(f.read())

for d in data:
    if d["model"] == "management.state":
        usr = controller.get_user_by_pk(d["fields"]["user"])
        print("user", usr.email)
        if d["fields"]["user_form_state"]:
            usr.state.user_form_state = "filled"
            print("Filled userform for user", d["fields"]["user"])
        else:
            usr.state.user_form_state = "unfilled"
            print("NOT Filled userform for user", d["fields"]["user"])
        usr.state.save()
