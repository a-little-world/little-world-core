from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, **options):
        from management.models.matches import Match
        from management.models.state import State
        from management.models.user import User
        from emails.models import EmailLog
        from django.db.models import Q
        from django.utils import timezone
        import datetime
        
        
        from emails import mails
        consider_only_registered_within_last_x_days = 40

        today = timezone.now()
        all_users_to_consider = User.objects.filter(
            ~(Q(state__user_category=State.UserCategoryChoices.SPAM) | Q(state__user_category=State.UserCategoryChoices.TEST)),
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            is_staff=False
        )
        
        x_days_ago = today - datetime.timedelta(days=consider_only_registered_within_last_x_days)
        all_users_to_consider = all_users_to_consider.filter(date_joined__gte=x_days_ago)
        
        def get_params(user):
            return mails.ImpulseBeitraegeParams(
                first_name=user.profile.first_name,
                link_url="https://rwth.zoom.us/j/95770913582?pwd=U3g5QWtCZXd3SFpxVC8zVmlWN1RtUT09",
                unsubscribe_url1="" # filled automatically
            )
            
        from management import controller
        print("check which users to send to or just send a test email? (Y/N)")
        user_input = input()
        

        if user_input == "Y":
            print("Sending emails...")
            users = list(all_users_to_consider)
            users = filter(lambda user: not (("oliver" in user.email) or ("rwth" in user.email) or ("berlin" in user.email) or ("hauptstadt" in user.email)), users)
            
            print("Collected", len(users), "users to send to")
            print("\n".join(map(lambda user: user.email, users)))
            print("send it ?( Y/N)")

            user_input = input()
            if user_input == "Y":
                controller.send_group_mail(
                    users=users,
                    subject="Impulsbeiträge zum Feierabend",
                    mail_name="impuls_beitraege",
                    mail_params_func=get_params,
                    unsubscribe_group="survery_requests"
                )
            else:
                print("Not send")
        else:
            print(f"Do nothing...")
            print("Send Test Email to herrduenschnlate+89@gmail.com (Y/N) ?")

            users = [controller.get_user_by_email("herrduenschnlate+89@gmail.com")]
            controller.send_group_mail(
                users=users,
                subject="Impulsbeiträge zum Feierabend",
                mail_name="impuls_beitraege",
                mail_params_func=get_params,
                unsubscribe_group="survery_requests"
            )
        