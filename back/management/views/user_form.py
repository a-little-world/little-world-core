from .cookie_banner_frontend import get_cookie_banner_template_data
from django.shortcuts import render, redirect
from django.utils.translation import pgettext_lazy
from django.conf import settings
from django.contrib.auth.decorators import login_required
from rest_framework import serializers
from dataclasses import dataclass
from django.urls import reverse
import json


def user_form_v2(request, **kwargs):

    return render(request, "user_form.html", {})