from django.test import TestCase
from translations import get_translation_catalog

valid_request_data = dict(email="benjamin.tim@gmx.de", first_name="Tim", second_name="Schupp", password1="Test123!", password2="Test123!", birth_year=1984)

valid_create_data = dict(
    email=valid_request_data["email"],
    password=valid_request_data["password1"],
    first_name=valid_request_data["first_name"],
    second_name=valid_request_data["second_name"],
    birth_year=valid_request_data["birth_year"],
)


class TestTranslations(TestCase):
    def _get_translations(self):
        return get_translation_catalog()

    def test_all_tags_translated(self):
        context = self._get_translations()

        print("Checking for untranslated tags")
