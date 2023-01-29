from management.tasks import send_new_message_notifications_all_users
from management.models import State, User


if False:
    users = User.objects.all()
    c = users.count()
    for u in users:
        c -= 1
        print(c)
        u.state.unread_messages_state = []
        u.state.save()
        print(u.email, u.state.unread_messages_state)


if True:
    send_new_message_notifications_all_users(
        False, False, True, False
    )
