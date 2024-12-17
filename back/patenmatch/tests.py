from django.test import TestCase
from rest_framework.test import APIRequestFactory
from patenmatch.api import PatenmatchUserViewSet
from patenmatch.models import PatenmatchUser
from emails.models import EmailLog
import time


# 'COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml exec backend sh -c "python3 manage.py test patenmatch.tests"'
class PatenmatchTests(TestCase):
    def test_register_patenmatch_user(self):
        factory = APIRequestFactory(enforce_csrf_checks=True)
        request = factory.post(
            "/api/patenmatch/user/",
            {"email": "herrduenschnlate+test1@gmail.com",
                "first_name": "Test",
                "last_name": "Test",
                "postal_code": "12345",
                "support_for": "individual",
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

        send_email_background("patenmatch-signup", user_id=pt_user.id, patenmatch=True)

        time.sleep(0.5)

        log = EmailLog.objects.filter(template="patenmatch-signup").first()

        print(log.data["params"])
