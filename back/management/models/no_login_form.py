from back import utils
from django.db import models
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.conf import settings
from management.api.no_login_form import StillInContactFormDataSerializer


class FormTypeChoices(models.TextChoices):
    STILL_IN_CONTACT = "still_in_contact"


class NoLoginForm(models.Model):
    hash = models.CharField(max_length=100, blank=True,
                            unique=True, default=utils._double_uuid)  # type: ignore

    form_type = models.CharField(choices=FormTypeChoices.choices,
                                 default=FormTypeChoices.STILL_IN_CONTACT,
                                 max_length=255)

    user = models.ForeignKey('User', on_delete=models.CASCADE)

    def get_link(self):
        return f"{settings.DJ_BASE_URL}/extform?form={self.hash}"


class StillInContactForm(models.Model):
    form = models.ForeignKey(
        NoLoginForm, on_delete=models.CASCADE, related_name="still_in_contact_form")
    user = models.ForeignKey(
        'User', on_delete=models.CASCADE, related_name="still_in_contact_form_user")

    still_in_contact = models.BooleanField(default=False)

    # TODO: more fields


FORMS = {
    FormTypeChoices.STILL_IN_CONTACT.value: {
        "serializer": StillInContactFormDataSerializer,
        "model": StillInContactForm
    }
}


def create_no_login_form(user, form_type) -> NoLoginForm:
    """
    This has to be called when a email with a no-login form is send. 
    This allowes us to generate a link like this:
    https://litte-world.com/extform?form=<from_hash> ( call get_link() on the NoLoginForm object )
    using this link we can then render and submit for data to that form without having the user to login.
    """
    return NoLoginForm.objects.create(user=user, form_type=form_type)
