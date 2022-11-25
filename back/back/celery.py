import os
from celery.signals import worker_ready
from celery import Celery, shared_task

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'back.settings')

app = Celery('back')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


@worker_ready.connect
def startup_task(sender, **k):
    print("started")
    return "Started"


@shared_task
def im_allive_task():
    from datetime import datetime
    print("> ", datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    print("=========================================")
    print("==== Server I'm happily chillin ;) ======")
    print("=========================================")


"""
All little world periodic tasks 
e.g.: notifying users that they have new messages
"""
app.conf.beat_schedule = {
    'im-allive-ping': {
        'task': 'back.celery.im_allive_task',
        'schedule': 60.0  # Every minute!
    }
}
