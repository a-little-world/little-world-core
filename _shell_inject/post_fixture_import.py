# To be run after the default fixture import
# We need to add all users to the matches of the default admin user
import json
from back.management import controller  # !dont_include
from back.management.models import User  # !dont_include
from back.management.models import rooms  # !dont_include
# !include from back.management.models import rooms
# !include from management import controller
# !include from back.management.models import User

with open("/app/old_backend_import_infos.json") as f:
    data = json.loads(f.read())

TOTAL_USER_PKS = data['total_users']

base_management_user = controller.get_base_management_user()
base_management_user.matches = list(range(2, TOTAL_USER_PKS + 1))
base_management_user.save()


# Now for users check this matches and create a video room for them it it doesn't exist
for usr in User.objects.all():
    for m in usr.state.matches:
        if not rooms.get_rooms_match(usr, m).exists():
            rooms.Room.objects.create(usr1=usr, usr2=m)

# Old images are automaticly downloaded into ./back/old_backend_p_images/*
# The info which image corresponds to which user is stored in ./back/old_backend_import_infos.json
user_image_map = data['user_image_map']

for pk in user_image_map:
    usr = User.objects.get(pk=pk)
    usr.profile.add_profile_picture_from_local_path(
        user_image_map[pk]["local_img_path"])
    usr.profile.save()

print("completed post fixture import!")
