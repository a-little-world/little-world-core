import json
# Loads all values from the old database into the current database
# dumpdata --indent --app management > db_management.json
# manage.py dumpdata --indent 2 management.profile
# loaddata --app management
with open("db.json") as f:
    data = json.loads(f.read())


USER_DATA_MAP = {}


def map_user_profile(model, pk, fields):

    def pop_filed(field_name):
        return fields.pop(field_name, None)

    def transform_user_type(user_type):
        if user_type == 0:
            return "volunteer"
        elif user_type == 1:
            return "learner"
        else:
            raise ValueError(f"Unknown user_type {user_type}")

    def transfrom_target_group(target_group):
        if target_group == 0:
            return "any"
        elif target_group == 1:
            return "refugee"
        elif target_group == 2:
            return "student"
        elif target_group == 3:
            return "worker"
        else:
            raise ValueError(f"Unknown target_group {target_group}")

    def typed_choice(choice, _user_type):
        return choice + ".vol" if _user_type == "volunteer" else ".ler"

    def transfrom_interests(interests):
        # TODO. check which input format interests actually has
        ORDERED_INTERESTS = ["art"]  # TODO ...
        return ",".join([ORDERED_INTERESTS[i] for i in interests.split(",")])

    def transfrom_avatar_config(avatar_config):
        # We stored them as json string before, now they are json fields in db
        # TODO: can they be empty?
        return json.loads(avatar_config)

    def transform_notification_channel(notification_channel):
        if notification_channel == 0:
            return "email"
        elif notification_channel == 1:
            return "sms"
        elif notification_channel == 2:
            return "call"
        else:
            raise ValueError(
                f"Unknown notification_channel {notification_channel}")

    def extract_and_transform_availability():
        DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]
        SLOTS = ["08_10", "10_12", "12_14", "14_16", "16_18", "18_20", "20_22"]
        availability = {d: [SLOTS[int(s)] for s in pop_filed(
            f'slots_{d}').split(",")] for d in DAYS}
        return availability

    def transform_liability(liability):
        if liability == 0:
            return "no"
        elif liability == 1:
            return "yes"
        else:
            raise ValueError(f"Unknown liability {liability}")

    user_type = transform_user_type(fields.pop("user_type"))

    return {
        "version": 1,  # TODO check if we can maybe just ignore this
        "user": "",  # TODO: this must match the pk of the user model
        "user_type": user_type,
        "target_group": typed_choice(transfrom_target_group(pop_filed("helping_group")), user_type),
        "additional_interests": pop_filed("additional_interests"),
        "phone_mobile": pop_filed("mobile_number"),
        "description": pop_filed("description"),
        "birth_year": pop_filed("birth_year"),
        "notify_channel": transform_notification_channel(pop_filed("notification_channel")),
        "availability": extract_and_transform_availability(),
        # image TODO this required extra handling since we might need to download the old image
        # created_at -> auto overwrite
        # updated_at -> auto overwrite
        ** fields  # We have already removed all transformed fields
    }


MAPPING_FUNCTIONS = {
    "user_management.userprofile": map_user_profile,
}

for element in data:
    model = element["model"]
    pk = element["pk"]
    fields = element["fields"]
    MAPPING_FUNCTIONS[model](model, pk, fields)
