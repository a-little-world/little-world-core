# This little hack here allowes me to use full syntax hightlighting and type checking without having the django project setup up
# Pylint doesn't globaly know the django apps, but it does recognize ./back as a package
# So when we prefix the import with back.--inport-- we get all the syntax suggar :)
import random
from back.management import controller  # !dont_include # used for syntax only
# !include from management import controller # this will be used on script execution
print(controller)


def random_names(amnt):
    first_names = ('John', 'Sean', 'Andy', 'Joe', 'Siobhan', 'Oliver', 'Tim')
    last_names = ('Johnson', 'Aachen', 'Smith', 'Williams',
                  'Berlin', 'Nuggets', 'Hendrix')
    names = []
    for i in range(amnt):
        names.append((random.choice(first_names), random.choice(last_names)))
    return names


valid_request_data = dict(
    email='test@user.de',
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


def _create_abunch_of_users(amnt=10):
    mail_count = 0
    mail_fragments = valid_create_data["email"].split("@")

    names = random_names(amnt)

    def _make_mail(count):
        count += 1
        return count, mail_fragments[0] + str(count) + "@" + mail_fragments[1]

    users = []
    for i in range(amnt):
        # 20 test users
        _data = valid_create_data.copy()
        mail_count, _mail = _make_mail(mail_count)
        print(f"Creating user: '{_mail}'")
        _data['email'] = _mail
        _data['first_name'] = names[i][0]
        _data['second_name'] = names[i][1]
        users.append(controller.create_user(
            **_data, send_verification_mail=False))
    return users


_create_abunch_of_users(amnt=20)
