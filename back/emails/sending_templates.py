from .mails import send_email, get_mail_data_by_name, SorryWeNeedMoreTimeToMatchYouMailParams


def sorry_still_need_some_matching_time_mail(to=["benjamin.tim@gmx.de"]):
    data = get_mail_data_by_name("we_need_some_more_time_for_matching")
    prms = SorryWeNeedMoreTimeToMatchYouMailParams(first_name="THE DUDE")
    send_email(
        subject="Little World – deine Suche & Gruppengespräche",
        recivers=to,
        mail_data=data,
        mail_params=prms,
        attachments=[],
        raise_exception=True,
        sender="oliver.berlin@little-world.com"
    )
