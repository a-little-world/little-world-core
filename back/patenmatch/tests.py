from django.test import TestCase
from rest_framework.test import APIRequestFactory
from patenmatch.api import PatenmatchUserViewSet
from patenmatch.models import PatenmatchUser, PatenmatchOrganization
from emails.models import EmailLog
import json
import time


# 'COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml exec backend sh -c "python3 manage.py test patenmatch.tests"'
class PatenmatchTests(TestCase):

    def test_patenmatch_matching_flow(self):
        # 1 - first we create an org, such that we can later match a user to it
        factory = APIRequestFactory(enforce_csrf_checks=False)
        
        org = PatenmatchOrganization.objects.create(
            name ="Cool Org",
            postal_code=12345,
            contact_first_name="Cool Contact",
            contact_second_name="Cool Contact",
            contact_email="herrduenschnlate+pt-contact@gmail.com",
            contact_phone="123234",
            maximum_distance=100,
            capacity=2,
            target_groups="family,child"
        )

        request = factory.post(
            "/api/patenmatch/user/",
            {
                "email": "herrduenschnlate+test1@gmail.com",
                "first_name": "Test",
                "last_name": "Test",
                "postal_code": 12345,
                "support_for": "family",
                "spoken_languages": "de,en",
                # "request_specific_organization": None
            },
        )

        response = PatenmatchUserViewSet.as_view({"post": "create"})(request)
        text = response.render().content.decode("utf-8")
        print(text)
        self.assertEqual(response.status_code, 201)
        time.sleep(0.5)

        pt_user = PatenmatchUser.objects.get(email="herrduenschnlate+test1@gmail.com")

        # Celery task sheduling doesn't work in tests, so we manually trigger thes task
        # ( that would in prod be triggered with POST /api/patenmatch/user/ )
        from management.tasks import send_email_background

        send_email_background(
            "patenmatch-signup", 
            user_id=pt_user.id, 
            patenmatch=True
        )

        time.sleep(0.5)

        log = EmailLog.objects.filter(template="patenmatch-signup").first()

        print(log.data["params"])
        
        # verification_link = log.data["params"]["patenmatch_email_verification_url"]
        # above would be the verification view url, but this cannot be rendered in tests
        # so instead we manually get the api url that would be called when rending that view
        verification_link = pt_user.get_verification_url()
        request = factory.get(verification_link)
        response = PatenmatchUserViewSet.as_view({"get": "verify_email"})(request)
        
        json_response = response.render().content.decode("utf-8")
        parsed_response = json.loads(json_response)
        print(parsed_response)
        assert parsed_response["match"] is not None
        match = parsed_response["match"]
        self.assertEqual(response.status_code, 200)
        
        org = PatenmatchOrganization.objects.get(id=int(match["id"]))
        
        context = {
            "organization_name": org.name,
            "patenmatch_first_name": pt_user.first_name,
            "patenmatch_last_name": pt_user.last_name,
            "patenmatch_email": pt_user.email,
            "patenmatch_target_group_name": pt_user.support_for,
            "patenmatch_postal_address": pt_user.postal_code,
            "patenmatch_language": pt_user.spoken_languages or "Not set"
        }
        
        print(context)
        
        send_email_background(
            "patenmatch-orga-forward-user", 
            user_id=org.id, 
            patenmatch=True, 
            patenmatch_org=True, 
            context=context
        )
        # TODO: check the email content asure that it contains all the user info
        
        