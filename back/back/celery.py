import os
import json
from datetime import datetime
from django.conf import settings
from celery.signals import worker_ready
from celery import Celery, shared_task

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'back.settings')

# CELERY_IMPORTS = [
#    "management.database_defaults.create_default_cookie_groups",
#    "management.database_defaults.create_default_community_events",
# ]

app = Celery('back', broker=settings.CELERY_BROKER_URL)

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
# app.autodiscover_tasks()
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@worker_ready.connect
def startup_task(sender, **k):
    return "Started " + datetime.now().strftime("%m/%d/%Y, %H:%M:%S")


@app.task(bind=True, name="im_allive_task")
def im_allive_task(self):
    print("> ", datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    print("=========================================")
    print("==== Server: I'm happily chilli'n ;) ====")
    print("=========================================")
    # return "RESULT" we don't return this as a result otherwise we would just be flooding the database


prod_shedules = {
    'new-message-notification': {
        'task': 'management.tasks.send_new_message_notifications_all_users',
        'schedule': 60.0 * 60.0  # Every hour
    },
    'generate-hourly-event-summary': {
        'task': 'management.tasks.write_hourly_backend_event_summary',
        'schedule': 60.0 * 60.0,  # Every hour
    },
    'generate-stats-series-day-grouped': {
        'task': 'management.tasks.create_series',
        'schedule': 60.0 * 60.0,  # Every hour
        'kwargs': {
            "regroup_by": "day"
        }
    },
    'generate-stats-series-hour-grouped': {
        'task': 'management.tasks.create_series',
        'schedule': 60.0 * 60.0,
        'kwargs': {
            "regroup_by": "hour"
        }
    },
    'generate-static-stats': {
        'task': 'management.tasks.collect_static_stats',
        'schedule': 60.0 * 60.0,  # Every hour
    }
}

"""
All little world periodic tasks 
e.g.: notifying users that they have new messages
"""
app.conf.beat_schedule = {
    'im-allive-ping': {
        'task': 'im_allive_task',
        'schedule': 60.0 * 5.0  # Every five minutes!
    },
    **(prod_shedules if settings.IS_PROD else {})
}
