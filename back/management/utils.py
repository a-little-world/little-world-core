import json

from celery.result import AsyncResult
from django.core.serializers.json import DjangoJSONEncoder


def check_task_status(task_id):
    """
    Check the status of a Celery task.
    
    Args:
        task_id: The ID of the Celery task
        
    Returns:
        dict: Task status information including state and info
    """
    task = AsyncResult(task_id)

    return {
        "state": task.state,
        "info": json.loads(json.dumps(task.info, cls=DjangoJSONEncoder, default=lambda o: str(o))),
    } 