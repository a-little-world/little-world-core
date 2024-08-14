import glob
import random
from . import controller  # this will be used on script execution
from management.models.profile import Profile


def random_names(amnt):
    first_names = ('John', 'Sean', 'Andy', 'Joe', 'Siobhan', 'Oliver', 'Tim')
    last_names = ('Johnson', 'Aachen', 'Smith', 'Williams',
                  'Berlin', 'Nuggets', 'Hendrix')
    names = []
    for i in range(amnt):
        names.append((random.choice(first_names), random.choice(last_names)))
    return names


valid_request_data = dict(
    email='herrduenschnlate+@gmail.com',
    first_name="?",  # We set them below,'?' would throw an error!
    second_name="?",
    password1='Test123!',
    password2='Test123!',
    birth_year=1984
)

valid_create_data = dict(
    email=valid_request_data['email'],
    password=valid_request_data['password1'],
    first_name=valid_request_data['first_name'],
    second_name=valid_request_data['second_name'],
    birth_year=valid_request_data['birth_year'],
)


def random_postal_code():
    return random.randint(10000, 99999)


def random_phone_number():
    return f'+49{random.randint(100000000, 999999999)}'


def random_availabilities():
    from management.validators import SLOTS, DAYS

    data = {}
    for day in DAYS:
        amount = random.randint(0, len(SLOTS))
        if amount == 0:
            data[day] = []
        else:
            data[day] = random.sample(SLOTS, amount)
    return data


def random_avatar():
    def rand_color():
        def r(): return random.randint(0, 255)
        return '#%02X%02X%02X' % (r(), r(), r())
    init = {
        "sex": "man",
        "faceColor": rand_color(),
        "earSize": "small",
        "eyeStyle": ["oval", "smile", "circle"],
        "noseStyle": ["long", "round", "short"],
        "mouthStyle": ["smile", "peace", "laugh"],
        "shirtStyle": ["short", "polo", "hoody"],
        "glassesStyle": ["none", "round"],
        "hairColor": rand_color(),
        "hairStyle": ["womanShort", "normal", "thick", "mohawk"],
        "hatStyle": ["none", "beanie", "turban"],
        "hatColor": rand_color(),
        "eyeBrowStyle": "up",
        "shirtColor": rand_color(),
        "bgColor": "linear-gradient(45deg, #ff1717 0%, #ffd368 100%)"
    }
    for k in init:
        if isinstance(init[k], list):
            init[k] = init[k][random.randint(0, len(init[k]) - 1)]
    return init


mail_fragments = valid_create_data["email"].split("@")


def _make_mail(count):
    count += 1
    return count, mail_fragments[0] + str(count) + "@" + mail_fragments[1]


pics = [f for f in glob.glob(
    "/back/dev_test_data/*") if not "management_user" in f]

# Just some stuff to generate some random sentances
# It will be more meaningfull if we have real words here for viewing in the frontend
nouns = ("puppy", "car", "rabbit", "girl", "monkey", "mohawk", "gorilla")
verbs = ("runs", "hits", "jumps", "drives", "barfs", "snapps", "kills")
adv = ("crazily.", "dutifully.", "foolishly.",
       "merrily.", "occasionally.", "foolishly")
adj = ("adorable", "clueless", "dirty", "odd", "stupid", "mad", "nugget")


def rand_descr(n=1):
    t = ""
    for i in range(n):
        num = random.randrange(0, 5)
        t += nouns[num] + ' ' + \
            verbs[num] + ' ' + adv[num] + ' ' + adj[num] + ' '
    return t


def random_choice(text_choices):
    return text_choices.values[
        random.randint(0, len(text_choices.values) - 1)]


profile_cls = Profile
user_form_choices = {
    "notify_channel": getattr(profile_cls, 'NotificationChannelChoices'),
    "user_type": getattr(profile_cls, 'TypeChoices'),
    "partner_location": getattr(profile_cls, 'ConversationPartlerLocation2'),
    "speech_medium": getattr(profile_cls, 'SpeechMediumChoices2'),
    "target_group": getattr(profile_cls, 'TargetGroupChoices2'),
    "partner_sex": getattr(profile_cls, 'ParterSexChoice'),
    "image_type": getattr(profile_cls, 'ImageTypeChoice'),
}


def create_test_user(i, user_seeds=None, password=None, email=None, pass_if_exists=False, send_verification_mail=False):
    # use user_seeds to generate redictable users
    if user_seeds:
        random.seed(user_seeds[i])  # Same user all?
    if user_seeds is None:
        random.seed(42)
    # 20 test users
    _data = valid_create_data.copy()
    mail_count, _mail = _make_mail(int(str(i)))
    if email is not None:
        _mail = email
        
    if pass_if_exists:
        try:
            usr = controller.get_user_by_email(_mail)
            if usr:
                return
        except:
            pass
        
    
    if password is not None:
        _data["password"] = password
    print(f"Creating user: '{_mail}'")
    _data['email'] = _mail
    random_name = random_names(1)[0]
    _data['first_name'] = random_name[0]
    _data['second_name'] = random_name[1]
    usr = controller.create_user(
        **_data, send_verification_mail=send_verification_mail)
    assert usr

    # Randomly fill out the user profile:
    usr.profile.description = rand_descr(n=2)
    usr.profile.language_skill_description = rand_descr(n=2)
    usr.profile.additional_interests = rand_descr(n=4)

    c = Profile.InterestChoices.values
    amnt_rand_interests = random.randint(0, len(c) - 1)
    interests = []
    for x in range(amnt_rand_interests):
        r = random.randint(0, len(c) - 1)
        interests.append(c[r])

    usr.profile.interests = interests
    usr.profile.availability = random_availabilities()
    print("TBS: availabilities", usr.profile.availability)
    for choice in user_form_choices:
        setattr(usr.profile, choice, random_choice(
            user_form_choices[choice]))
    print("TBS: image type choice", usr.profile.image_type)
    if usr.profile.image_type == Profile.ImageTypeChoice.AVATAR:
        usr.profile.avatar_config = random_avatar()
    else:
        usr.profile.add_profile_picture_from_local_path(
            pics[random.randint(0, len(pics) - 1)])

    if usr.profile.partner_location == Profile.ConversationPartlerLocation2.CLOSE:
        # In this case the user is required to have a postal code
        usr.profile.postal_code = str(random_postal_code())
    if usr.profile.notify_channel != \
            Profile.NotificationChannelChoices.EMAIL:
        usr.profile.phone_mobile = str(random_phone_number())
    usr.profile.save()
    # This will set the profile to completed
    completed, msgs = usr.profile.check_form_completion()
    print("TBS", msgs)
    # & it will automaticly trigger the score calulation for that user
    
    us = usr.state
    us.email_authenticated = True
    us.had_prematching_call = True
    us.save()

    # Cool thing, we can actuly set them a profile picture from currently inside the container!
    return usr


def create_abunch_of_users(amnt=30, user_seeds=[42]*20):
    # We can for now just create a range of seeds,
    # thereby it will give use the same rando users everytime!
    user_seeds = list(range(amnt))
    mail_count = 0

    users = []
    for i in range(amnt):
        users.append(create_test_user(i, user_seeds, pass_if_exists=True))
        

    # Match them all with each other
    # Randomly match some of the users:
        
    return users


def modify_profile_to_match(usr1, usr2):
    """
    Modifies two user profiles so that they are matching 
    """
    u1_p = usr1.profile
    u2_p = usr2.profile

    u1_p.user_type = Profile.TypeChoices.VOLUNTEER
    u2_p.user_type = Profile.TypeChoices.LEARNER

    u1_p.partner_location = Profile.ConversationPartlerLocation2.ANYWHERE
    u2_p.partner_location = Profile.ConversationPartlerLocation2.ANYWHERE

    u1_p.target_group = Profile.TargetGroupChoices2.ANY
    u2_p.target_group = Profile.TargetGroupChoices2.ANY

    u1_p.speech_medium = Profile.SpeechMediumChoices2.ANY
    u2_p.speech_medium = Profile.SpeechMediumChoices2.ANY

    u1_p.save()
    u2_p.save()
