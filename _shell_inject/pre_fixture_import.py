# to be injected before old database fixture import
# This creates two default admin users
import os
from back.management import controller  # !dont_include
# !include from management import controller
# This automaticly creates the default admin user:
controller.get_base_management_user()

# Now we also create a special user for tim :)
controller.create_user(
    email="tim@timschupp.de",
    password=os.environ.get("DJ_TIM_TEST_USER_PASSWORD", "Test123!"),
    first_name="Jim",
    second_name="Tupp",
    birth_year=1984,
    send_verification_mail=False,
    send_welcome_notification=False,
    send_welcome_message=False,
)
