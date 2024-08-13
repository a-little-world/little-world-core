def first_name(user):
    return user.profile.first_name

def partner_first_name(user, match):
    partner = match.get_partner(user)
    return partner.profile.first_name

def verification_code(user):
    return "123456"

def unsubscribe_url(user):
    return "https://www.example.com/unsubscribe"