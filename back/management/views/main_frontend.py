from ..api.user_data import get_full_frontend_data
from django.contrib.auth.mixins import LoginRequiredMixin
from back.utils import CoolerJson
from django.conf import settings
import json
from dataclasses import dataclass, field
from django.shortcuts import render, redirect
from django.urls import reverse
from rest_framework.request import Request
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework import serializers
from django.views import View
from rest_framework.response import Response
from typing import List, Optional
from tracking import utils
from tracking.models import Event


# The following two are redundant with api.admin.UserListParams, api.admin.UserListApiSerializer
# But that is desired I wan't to always handle admin logic seperately this might come in handy in the future

@dataclass
class MainFrontendParams:
    filters: 'list[str]' = field(default_factory=list)
    paginate_by: int = 50
    order_by: Optional[str] = None  # Use default order per default
    page: int = 1


class MainFrontendParamsSerializer(serializers.Serializer):
    # All these parameters are only allowed for admins!
    filters = serializers.ListField(required=False)
    paginate_by = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    order_by = serializers.CharField(required=False)

    def create(self, validated_data):
        return MainFrontendParams(**validated_data)


class MainFrontendView(LoginRequiredMixin, View):
    login_url = ('https://home.little-world.com/' if settings.IS_PROD else '/login') if (not settings.USE_LANDINGPAGE_REDIRECT) else settings.LANDINGPAGE_REDIRECT_URL
    redirect_field_name = 'next'

    @utils.track_event(name=_("Render User Form"), event_type=Event.EventTypeChoices.REQUEST, tags=["frontend"])
    def get(self, request, **kwargs):
        """
        Entrypoint to the main frontend react app.
        1. check if email verified, if not redirect to views.form.email_verification
        2. check if user form filled, if not redirect to views.from.user_form

        TODO this **will** change, 
        at some point we will allow to use the main app even without having your email verified
        """

        # This is a regular django view,
        # but since we still wan't to use serialization from DRF
        # We will wrap the 'request' into a DRF.request
        # This gives us json parsed .data and .query_set options
        drf_request = Request(request=request)

        if not request.user.is_staff and len(drf_request.query_params) != 0:
            # TODO: this check doesn't seems to work
            return Response(_('Query param usage on main view only allowed for admins!'), status=status.HTTP_403_FORBIDDEN)

        serializer = MainFrontendParamsSerializer(
            data=drf_request.query_params)  # type: ignore

        if not serializer.is_valid():
            # Since this is a regular django view we have to return the erros manually
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        params = serializer.save()
        print("PRMS: " + str(params))

        if not request.user.state.is_email_verified():
            return redirect(reverse("management:email_verification", kwargs={}))

        if not request.user.state.is_user_form_filled():
            return redirect(reverse("management:user_form", kwargs={}))

        _kwargs = params.__dict__
        _kwargs.pop("filters")  # TODO: they are not yet supported
        _kwargs.pop("order_by")  # TODO: they are not yet supported
        from django.utils import translation

        # we want this view to pass tags by default,
        # the frontend also receives all api translations!
        # This way it can switch the language without reloading
        with translation.override("tag"):
            profile_data = get_full_frontend_data(
                request.user, options=True, **_kwargs, admin=request.user.is_staff)
        return render(request, "main_frontend.html", {"profile_data": json.dumps(profile_data, cls=CoolerJson)})
