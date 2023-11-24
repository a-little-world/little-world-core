from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, **options):
        from management.models import Match, State, User
        from emails.models import EmailLog
        from django.db.models import Q
        
        prev_suvery_emails = ["survey_aniq_2", "survey3_natalia",  "multi_user_interview_request_5"]
        
        emails = EmailLog.objects.filter(Q(template__in=prev_suvery_emails) & Q(sucess=True)).values_list("receiver", flat=True)
        
        non_support_matches = Match.objects.filter(
            Q(confirmed=True) & Q(active=True) & Q(support_matching=False)
        ).distinct()
        
        
        learns_that_had_a_match = User.objects.filter(
            Q(match_user1__in=non_support_matches) | 
            Q(match_user2__in=non_support_matches)
        ).filter(
            profile__user_type="learner"
        ).distinct().order_by('-date_joined')
        
        # TODO somethings wrong with this
        learers_that_have_unsubscibed = User.objects.filter(
            settings__email_settings__unsubscibed_options__contains=["survery_requests"]
        )
        
        learns_that_have_no_received_prev_suvery_emails = learns_that_had_a_match.filter(
            ~Q(id__in=emails)
        )
        
        print("Found ", len(learns_that_had_a_match), " learners that had a match")
        print("Found ", len(learers_that_have_unsubscibed), " learners that have unsubscibed")
        print("Found", len(learns_that_have_no_received_prev_suvery_emails), "learners that have not received the prev suvery emails")

        print("Do you want to send the survey to these users? (Y/N)")
        user_input = input()
        
        from emails import mails
        
        def get_params(user):
            return mails.GeneralSurveryMailParams(
                first_name=user.profile.first_name,
                link_url="https://tally.so/r/w47d7A",
                unsubscribe_url1="" # filled automatically
            )
            
        from management import controller

        if user_input == "Y":
            print("Sending emails...")
            users = list(learns_that_have_no_received_prev_suvery_emails)

            controller.send_group_mail(
                users=users,
                subject="Umfrage zur Verbesserung von Little World",
                mail_name="general_interview_03_11",
                mail_params_func=get_params,
                unsubscribe_group="survery_requests"
            )
        else:
            print(f"Do nothing...")
            print("Send Test Email to herrduenschnlate+test-mail@gmail.com (Y/N) ?")

            users = [controller.get_user_by_email("herrduenschnlate+test-mail@gmail.com")]
            controller.send_group_mail(
                users=users,
                subject="Umfrage zur Verbesserung von Little World",
                mail_name="general_interview_03_11",
                mail_params_func=get_params,
                unsubscribe_group="survery_requests"
            )
        