from django.test import TestCase
from rest_framework.test import RequestsClient
import json
from rest_framework.response import Response
from django.conf import settings
from management.models import profile
from rest_framework.test import APIRequestFactory, force_authenticate
from .. import api

valid_request_data = dict(
    email='benjamin.tim@gmx.de',
    first_name='Tim',
    second_name='Schupp',
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

from translations import get_translation_catalog

class TestTranslations(TestCase):

    def _get_translations(self):
        return get_translation_catalog()

    def test_all_tags_translated(self):
        """ 
        This test will error if a developer has defined a new translation string using pgettext(tag, string)
        But has not trasnlated it to all laguages
        ---> In the future this test might be ignored, 
        but for now this is a good check so that there will never be a trasnlation tag in the frontend which is not translated!
        """
        context = self._get_translations()

        non_tag_lang = [l[0] for l in settings.LANGUAGES if l[0] != "tag"]
        missing_trans = {l: [] for l in non_tag_lang}
        for k in context["tag"]:
            for lang in non_tag_lang:
                if k not in context[lang]:
                    missing_trans[lang].append(k)

        print("MISSING", missing_trans)
        assert all([len(missing_trans[l]) == 0 for l in non_tag_lang]
                   ), f"There are missing translations:\n" \
            + '\n'.join([f"Lang: '{l}':\n" + '\n'.join([t for t in missing_trans[l]])
                        for l in non_tag_lang])
