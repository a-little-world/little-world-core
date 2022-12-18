import json
# Loads all values from the old database into the current database
# dumpdata --indent --app management > db_management.json
# manage.py dumpdata --indent 2 management.profile
# loaddata --app management


USER_DATA_MAP = {}
USERS_THAT_REQUIRE_IMAGE_REUPLOAD = []


def map_user_profile(model, pk, fields):

    def pop_filed(field_name):
        return fields.pop(field_name)

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
        ORDERED_INTERESTS = ["sport", "art", "music", "literature",
                             "video", "fashion", "culture",
                             "travel", "food", "politics", "nature",
                             "science", "technology", "history", "religion",
                             "sociology", "family", "psycology", "personal-development"]
        return ",".join([ORDERED_INTERESTS[int(i)] for i in interests.split(",") if i != ""])

    def transfrom_avatar_config(avatar_config):
        # We stored them as json string before, now they are json fields in db
        # TODO: can they be empty?
        print("TBS: config", avatar_config)
        return json.loads(avatar_config) if avatar_config is not None and avatar_config != "" and avatar_config.lower() != "none" else {}

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

        def lookup_slots(slots):
            _s = []
            for s in slots:
                if s == "no_slot_trans":
                    pass
                elif int(s) == 0:
                    pass
                elif int(s) >= 1:
                    _s.append(SLOTS[int(s) - 1])
            return _s

        availability = {d: lookup_slots(pop_filed(
            f'slots_{d}').split(",")) for d in DAYS}
        return availability

    def transform_liability(liability):
        if liability == 0:
            return "no"
        elif liability == 1:
            return "yes"
        else:
            raise ValueError(f"Unknown liability {liability}")

    def transform_partner_sex(sex):
        if sex == 0:
            return "any"
        elif sex == 1:
            return "male"
        elif sex == 2:
            return "female"
        else:
            raise ValueError(f"Unknown sex {sex}")

    def transform_speech_medium(speech_medium):
        if speech_medium == 0:
            return "phone"
        elif speech_medium == 1:
            return "video"
        elif speech_medium == 2:
            return "any"
        else:
            raise ValueError(f"Unknown speech medium {speech_medium}")

    def transform_partner_location(partner_location):
        if partner_location == 0:
            return "anywhere"
        elif partner_location == 1:
            return "close"
        elif partner_location == 2:
            return "far"

    user_type = transform_user_type(fields.pop("user_type"))

    def transfrom_liability(liability):
        if liability == 0:
            return "no"
        elif liability == 1:
            return "yes"
        else:
            raise ValueError(f"Unknown liability {liability}")

    def transform_lang_level(lang_level):
        return "level-" + str(lang_level)

    def transfrom_image_type(image_type):
        if image_type == 0:
            return "image"
        elif image_type == 1:
            return "background"
        else:
            raise ValueError(f"Unknown image_type {image_type}")

    user = pop_filed("user")
    profile_img_url = pop_filed("profile_image")
    if profile_img_url != "":
        USERS_THAT_REQUIRE_IMAGE_REUPLOAD.append({
            "usr_pk": user,
            "old_image_url": profile_img_url,
        })
        pass

    transformed_data = {
        "version": 0,  # Version 0 is a marker old backend imported profiles
        "created_at": pop_filed("created_at"),
        "updated_at": pop_filed("updated_at"),
        "first_name": pop_filed("first_name"),
        "second_name": pop_filed("second_name"),
        "birth_year": pop_filed("birth_year"),
        "user_type": user_type,
        # "past_user_types": None, django will set defaults here
        "target_group": typed_choice(transfrom_target_group(pop_filed("helping_group")), user_type),
        "partner_sex": transform_partner_sex(pop_filed('partner_sex')),
        "speech_medium": transform_speech_medium(pop_filed('conversation_medium')),
        "partner_location": typed_choice(transform_partner_location(pop_filed('partner_location')), user_type),
        "postal_code": pop_filed("postal_code"),
        "interests": transfrom_interests(pop_filed("interests")),
        "additional_interests": pop_filed("additional_interests"),
        "availability": extract_and_transform_availability(),
        "liability": transform_liability(pop_filed("liability")),
        "notify_channel": transform_notification_channel(pop_filed("notification_channel")),
        "phone_mobile": pop_filed("mobile_number"),
        "description": pop_filed("description"),
        "language_skill_description": pop_filed("language_skill_description"),
        "lang_level": typed_choice(transform_lang_level(pop_filed("language_level")), user_type),
        "image_type": transfrom_image_type(pop_filed("profile_image_type")),
        "image":  profile_img_url,
        "avatar_config": transfrom_avatar_config(pop_filed("profile_avatar")),
        # v- NOTE this is the user id never mix this up!
        "user": user,
    }
    return transformed_data


def map_user_state(model, pk, fields):

    def pop_filed(field_name):
        return fields.pop(field_name, None)

    def transform_user_category(user_category):
        if user_category == 0:
            return "undefined"
        elif user_category == 1:
            return "spam"
        elif user_category == 2:
            return "legit"
        elif user_category == 3:
            return "test"
        else:
            raise ValueError(f"Unknown user_category {user_category}")

    def transform_user_form_sate(user_form_state):
        if user_form_state == 0:
            return False
        elif user_form_state == 1:
            return True
        else:
            raise ValueError(f"Unknown user_form_state {user_form_state}")

    def transform_email_auth_state(email_auth_state):
        if email_auth_state == 0:
            return "unauthenticated"
        elif email_auth_state == 1:
            return "authenticated"

    def transform_matching_state(matching_state):
        if matching_state == 0:
            return "idle"
        elif matching_state == 1:
            return "searching"
        elif matching_state == 2:
            return "idle"
        elif matching_state == 3:
            return "searching"
        else:
            raise ValueError(f"Unknown matching_state {matching_state}")

    def transform_unconfirmed_matches(unconfirmed_matches):
        return unconfirmed_matches  # TODO we should insert the hashes instead of the ids here

    user_state = {
        "user": pop_filed("user"),
        "created_at": pop_filed("created_at"),
        "updated_at": pop_filed("updated_at"),
        "user_form_state": transform_user_form_sate(pop_filed("user_form_state")),
        "email_authenticated": transform_user_form_sate(pop_filed("email_verification_state")),
        "email_auth_pin": pop_filed("email_verificaton_code"),
        "matching_state": transform_matching_state(pop_filed("matching_state")),
        "matches": pop_filed("matches"),
        "user_category": transform_user_category(pop_filed("user_category")),
        "unconfirmed_matches_stack": transform_unconfirmed_matches(pop_filed("unconfirmed_matches")),
        "unread_chat_message_count": pop_filed("last_new_message_count"),
        "unread_chat_message_count_update_time": pop_filed("last_time_last_message_count_update"),
    }
    return user_state


def map_user(model, pk, fields):
    user_email = fields.pop("email")
    user_model_data = {
        "password": fields.pop("password"),
        "last_login": fields.pop("last_login"),
        "is_superuser": fields.pop("is_superuser"),
        "first_name": "",  # TODO: this sould be populated from the corresponding profile
        "last_name": "",  # TODO: this sould be populated from the corresponding profile
        "is_staff": fields.pop("is_staff"),
        "is_active": fields.pop("is_active"),
        "date_joined": fields.pop("date_joined"),
        "email": user_email,
        "username": user_email,
        # hash: we can leave this blank django will auto generate a hash!
        "old_backend_user_h256_pk": fields.pop("user_h256_pk"),
        "groups": [],
        "user_permissions": [],
    }
    return user_model_data


def map_dialogs(model, pk, fields):
    pass


def map_messages(model, pk, fields):
    pass

# TODO: we shall not forget to create the video rooms!


MAPPING_FUNCTIONS = {
    "user_management.userprofile": {
        "f": map_user_profile,
        "model": "management.profile"
    },
    "user_management.userstate": {
        "f": map_user_state,
        "model": "management.state"
    },
    "user_management.user": {
        "f": map_user,
        "model": "management.user"
    }
}

MODELS = []
PK_USER_DATA_MAP = {}

if __name__ == "__main__":

    with open("user_management_db_dump.json") as f:
        # with open("test_userprofile.json") as f:
        data = json.loads(f.read())

    def update_pk_model_reference(pk, model, m_data):
        if pk in PK_USER_DATA_MAP:
            PK_USER_DATA_MAP[pk][MAPPING_FUNCTIONS[model]
                                 ["model"]] = m_data
        else:
            PK_USER_DATA_MAP[pk] = {}
            PK_USER_DATA_MAP[pk][MAPPING_FUNCTIONS[model]
                                 ["model"]] = m_data

    for element in data:
        model = element["model"]
        pk = element["pk"]
        fields = element["fields"]
        if model not in MAPPING_FUNCTIONS:
            print("WARNING: ", f"Model {model} is not mapped!", "Skipping...")
            continue
        print(model, pk, "Field names: ", list(fields.keys()))
        m_data = {
            "model": MAPPING_FUNCTIONS[model]["model"],
            "pk": pk,
            "fields": MAPPING_FUNCTIONS[model]["f"](model, pk, fields)
        }
        MODELS.append(m_data)
        if model == "user_management.user":
            update_pk_model_reference(pk, model, m_data)
        elif model in ["user_management.userprofile", "user_management.userstate"]:
            usr_pk = m_data["fields"]["user"]
            update_pk_model_reference(usr_pk, model, m_data)

        print("========>", f"Extracted {model} for user {pk}")

    # After the inital extraction we need to perform some post updates
    # 1. we need to take last and first name fom the user model and ad it to their profile model
    for model in MODELS:
        if model["model"] == "management.user":
            user_pk = model["pk"]
            print("User pk: ", user_pk)
            print("User data: ", PK_USER_DATA_MAP[user_pk])
            user_profile = PK_USER_DATA_MAP[user_pk]["management.profile"]
            model["fields"]["first_name"] = user_profile["fields"]["first_name"]
            model["fields"]["last_name"] = user_profile["fields"]["second_name"]

    print(json.dumps(MODELS, indent=4))

    # we write the results to ./back/transformed_fixture.json
    # Try inport via: ./run.py ma loaddata ./transformed_fixture.json
    with open("./back/transformed_fixture.json", "w") as f:
        f.write(json.dumps(MODELS, indent=4))

    """
    How to perform the import? 
    1. create the default base management user (pk=1)
    2. Make sure the old basemangement user is overwritten (old pk=1) ( Delete is from the transformed fixture!)
    3. Make sure to overwrite the old second admin user (pk=2) with a regular user
    4. Load all other users! They all should already have a match with the default management user (pk=1)
    5. Load all dialogs and chat messages
    6. For all matches, create a new video room
    7. For all users that had a profile image url set, download the profile image and upload it to the new bucket
    8. Calculate the new match score for all users 

    ...Test integiry login with some users check if all messages are listed as expected
    """
