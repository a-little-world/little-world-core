import urllib.parse

from django.conf import settings
from django.utils import timezone
from management.models.pre_matching_appointment import PreMatchingAppointment
from patenmatch.models import PatenmatchUser
from management.api.match_journey_filters import completed_match


def first_name(user):
    return user.profile.first_name


def partner_first_name(user, match):
    assert (user == match.user1) or (user == match.user2)
    partner = match.get_partner(user)
    return partner.profile.first_name


def partner_profile_url(user, match):
    assert (user == match.user1) or (user == match.user2)
    partner = match.get_partner(user)
    return f"{settings.BASE_URL}/app/profile/{partner.hash}"


def verification_code(user):
    return user.state.email_auth_pin


def restart_search_url(user):
    return f"{settings.BASE_URL}/app"


def verification_url(user):
    return f"{settings.BASE_URL}/mailverify_link/{user.state.get_email_auth_code_b64()}"


def accept_match_url(user, proposed_match=None):
    assert (user == proposed_match.user1) or (user == proposed_match.user2)
    return f"{settings.BASE_URL}/login?next=/app/"


def proposed_match_first_name(user, proposed_match=None):
    assert (user == proposed_match.user1) or (user == proposed_match.user2)
    partner = proposed_match.get_partner(user)
    return partner.profile.first_name


def reset_password_url(user=None, match=None, context={"reset_password_url": "Not set"}):
    return context["reset_password_url"]


def confirm_in_contact_url(user, match):
    assert (user == match.user1) or (user == match.user2)
    # TODO: correct link
    return f"{settings.BASE_URL}/login?next=/app/"


def user_form_url(user):
    return f"{settings.BASE_URL}/app/user-form/"


def messages_url(user):
    return f"{settings.BASE_URL}/app/chat/"


def link_url(user=None, match=None, context={"link_url": "Not set"}):
    return context["link_url"]


def unsubscribe_url(user):
    return f"{settings.BASE_URL}/email-preferences/{user.settings.email_settings.hash}/"


def date():
    return str(timezone.now())


def patenmatch_email_verification_url(user):
    assert isinstance(user, PatenmatchUser)
    return settings.PATENMATCH_URL + user.get_verification_view_url()


def patenmatch_organization_name(user=None, context={"patenmatch_organization_name": "Not set"}):
    return context["patenmatch_organization_name"]


def patenmatch_first_name(user=None, context={"patenmatch_first_name": None}):
    if context["patenmatch_first_name"] is not None:
        return context["patenmatch_first_name"]
    assert isinstance(user, PatenmatchUser)
    return user.first_name


def patenmatch_last_name(user=None, context={"patenmatch_last_name": None}):
    if context["patenmatch_last_name"] is not None:
        return context["patenmatch_last_name"]
    assert isinstance(user, PatenmatchUser)
    return user.last_name


def patenmatch_email(user=None, context={"patenmatch_email": None}):
    if context["patenmatch_email"] is not None:
        return context["patenmatch_email"]
    assert isinstance(user, PatenmatchUser)
    return user.email


def patenmatch_target_group_name(user=None, context={"patenmatch_target_group_name": None}):
    if context["patenmatch_target_group_name"] is not None:
        return context["patenmatch_target_group_name"]
    assert isinstance(user, PatenmatchUser)
    return user.support_for


def patenmatch_postal_address(user=None, context={"patenmatch_postal_address": None}):
    if context["patenmatch_postal_address"] is not None:
        return context["patenmatch_postal_address"]
    assert isinstance(user, PatenmatchUser)
    return user.postal_code


def patenmatch_language(user=None, context={"patenmatch_language": None}):
    if context["patenmatch_language"] is not None:
        return context["patenmatch_language"]
    assert isinstance(user, PatenmatchUser)
    return user.spoken_languages


def prematching_datetime(user, context={"appointment": None}):
    if context["appointment"] is None:
        appointment = PreMatchingAppointment.objects.filter(user=user).first()
    else:
        appointment = context["appointment"]
    return appointment.start_time.strftime("%d.%m.%Y um %H:%M Uhr")


def prematching_booking_link(user):
    return "https://cal.com/" + "{calcom_meeting_id}?{encoded_params}".format(
        encoded_params=urllib.parse.urlencode(
            {
                "email": str(user.email),
                "hash": str(user.hash),
                "bookingcode": str(user.state.prematch_booking_code),
            }
        ),
        calcom_meeting_id=settings.DJ_CALCOM_MEETING_ID,
    )


def still_in_contact_yes_url(user, match, **kwargs):
    """
    Generate URL for confirming continued contact with match partner outside the platform
    """
    base_url = settings.BASE_URL
    token = "TODO" # TODO generate_token_for_user(user_id)
    return f"{base_url}/still-in-contact/yes/{match.id}?token={token}"

def still_in_contact_no_url(user, match, **kwargs):
    """
    Generate URL for indicating no continued contact with match partner
    """
    base_url = settings.BASE_URL
    token = "TODO" # TODO generate_token_for_user(user_id)
    return f"{base_url}/still-in-contact/no/{match.id}?token={token}"


def latest_completed_match_first_name(user):
    from django.db.models import Q
    completed_matches = completed_match().filter(
        Q(user1=user) | Q(user2=user)
    )
    if completed_matches.count() == 0:
        return "..."

    return completed_matches.order_by('-created_at').first().get_partner(user).profile.first_name
