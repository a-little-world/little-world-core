from back.management import controller  # !dont_include
from back.management.models import User  # !dont_include
from back.management.models import rooms  # !dont_include
# !include from management.models import rooms
# !include from management import controller
# !include from management.models import User

for user in User.objects.all():
    unconf = user.state.unconfirmed_matches_stack
    new_unconf = None
    for hash in unconf:
        try:
            usr_id = int(hash)
            print(user.email, "has some ids in unconfirmed", usr_id)
            orig_user = controller.get_user_by_pk(usr_id)
            if new_unconf is None:
                new_unconf = []
            new_unconf.append(orig_user.hash)
            print("Fixing this => ", orig_user.hash)
        except:
            pass  # Then its a hash and all is fine

    if new_unconf:
        user.state.unconfirmed_matches_stack = new_unconf
        user.state.save()
        print("REplacing with ", new_unconf)
