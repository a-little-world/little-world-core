import os
from datetime import datetime

from celery import Celery
from celery.signals import task_postrun, worker_ready
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "back.settings")

# CELERY_IMPORTS = [
#    "management.database_defaults.create_default_cookie_groups",
#    "management.database_defaults.create_default_community_events",
# ]

app = Celery("back", broker=settings.CELERY_BROKER_URL)

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
# app.autodiscover_tasks()
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


@worker_ready.connect
def startup_task(sender, **k):
    return "Started " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S")


@task_postrun.connect
def close_db_connections_after_task(**kwargs):
    """
    Automatically close all database connections after each task completes.
    This prevents connection exhaustion by ensuring connections don't stay
    open for CONN_MAX_AGE (600s) after task completion.
    Whilist A high connection time out is desirable for the API endpoints, as then the backend re-uses connections.
    """
    from django import db

    db.connections.close_all()


@app.task(bind=True, name="im_allive_task")
def im_allive_task(self):
    print("> ", datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    print("=========================================")
    print("==== Server: I'm happily chilli'n ;) ====")
    print("=========================================")


auto_emails = {
    "check-match-proposals-expire-and-send-mails": {
        "task": "management.tasks.check_prematch_email_reminders_and_expirations",
        "schedule": 60.0 * 60.0,  # Every hour
    },
    "check-registration-reminders": {
        "task": "management.tasks.check_registration_reminders",
        "schedule": 60.0 * 60.0,  # Every hour
    },
}


if os.environ.get("DJ_ENABLE_AUTO_EMAILS__U023_U024_U025", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-u023-u024-u025": {
                "task": "management.tasks.automatic_emails_u023_u024_u025",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__M12_M13_M14", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-m12-m13-m14": {
                "task": "management.tasks.automatic_emails_m12_m13_m14",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__M023", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-m023": {
                "task": "management.tasks.automatic_emails_m023",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__M024_M025", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-m024-m025": {
                "task": "management.tasks.automatic_emails_m024_m025",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__M031_M032_M033_M042", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-m031-m032-m033-m042": {
                "task": "management.tasks.automatic_emails_m031_m032_m033_m042",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__U072_U073_U074", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    auto_emails.update(
        {
            "automatic-emails-u072-u073-u074": {
                "task": "management.tasks.automatic_emails_u072_u073_u074",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )

if os.environ.get("DJ_ENABLE_AUTO_EMAILS__U081_U082_U083_U084", "false").lower() in ("true", "1", "t"):
    # TODO: Remove once in prod for a while without bugs
    # The 81 email is handeled inside the api that change the searching state of the user
    auto_emails.update(
        {
            "automatic-emails-u082-u083-u084": {
                "task": "management.tasks.automatic_emails_u082_u083_u084",
                "schedule": 60.0 * 60.0 * 6.0,  # every 6 hours
            }
        }
    )
prod_shedules = {
    "record-bucket-statistics": {
        "task": "management.tasks.record_bucket_ids",
        "schedule": 60.0 * 60.0 * 24.0,  # once a day
    },
    "hourly-check-banner-activation": {
        "task": "management.tasks.hourly_check_banner_activation",
        "schedule": 60.0 * 60.0,  # every hour
    },
    "daily-fix-unusually-long-livekit-sessions": {
        "task": "video.tasks.daily_fix_unusually_long_livekit_sessions",
        "schedule": 60.0 * 60.0 * 24.0,  # once a day
    },
}

prod_shedules.update(auto_emails)

"""
All little world periodic tasks 
e.g.: notifying users that they have new messages
"""
if not settings.PROD_ATTACH:
    # If we are just atteching to the db of a prod pod we don't want any celery beat shedules
    app.conf.beat_schedule = {
        "im-allive-ping": {
            "task": "im_allive_task",
            "schedule": 60.0 * 5.0,  # Every five minutes!
        },
        **(prod_shedules if settings.IS_PROD else {}),
    }

"""
Helper function to end a celery task using the AsyncResult ID
"""


def end_task(task_id):
    app.control.revoke(task_id)
