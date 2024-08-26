from django.test import TestCase
from management.controller import create_user, match_users
from management.tests.helpers import valid_profile_data


class AdminApiTests(TestCase):
    def _create_abunch_of_users(self, amnt=20):
        mail_count = 0
        mail_fragments = valid_profile_data["email"].split("@")

        def _make_mail(count):
            count += 1
            return count, mail_fragments[0] + str(count) + "@" + mail_fragments[1]

        users = []
        for i in range(amnt):
            # 20 test users
            _data = valid_profile_data.copy()
            mail_count, _mail = _make_mail(mail_count)
            print(f"Creating user: '{_mail}'")
            _data["email"] = _mail
            users.append(create_user(**_data))
        return users

    def _match_all(self, users):
        # Matches *all* user in the users list
        stack = users.copy()
        while len(stack) > 1:
            usr = stack.pop(len(stack))  # begin at the highest index
            for _usr in stack:
                match_users({usr, _usr})

    # def test_management_user_created(self): TODO

    def test_matches_made(self):
        users = self._create_abunch_of_users(amnt=20)
        # TODO: check if matches are created

    def test_user_list(self):
        pass
