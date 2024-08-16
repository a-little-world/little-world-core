from django.conf import settings


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


def verification_url(user):
    return f"{settings.BASE_URL}/api/user/verify/email/{user.state.get_email_auth_code_b64()}"


def accept_match_url(user, match):
    assert (user == match.user1) or (user == match.user2)
    return f"{settings.BASE_URL}/login?next=/app/"


def reset_password_url(user=None, match=None, context={"reset_password_url": "Not set"}):
    return context["reset_password_url"]


def unsubscribe_url(user):
    return "https://www.example.com/unsubscribe"
