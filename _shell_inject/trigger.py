from management.tasks import send_new_message_notifications_all_users
send_new_message_notifications_all_users(
    filter_out_base_user_messages=True,
    do_send_emails=True,
    do_write_new_state_to_db=True,
    send_only_if_logged_in_withing_last_3_weeks=True
)
