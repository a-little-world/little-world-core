import logging

from django.db import IntegrityError

from management.tasks import send_meta_capi_events
from tracking.models import ConversionEventLog

logger = logging.getLogger(__name__)


def queue_meta_event_once(event, metadata=None) -> bool:
    """
    Queues a Meta CAPI event once based on unique event_id.

    Returns:
        True if queued.
        False if already queued/sent before.
    """
    event_name = event.get("event_name")
    event_id = event.get("event_id")

    if not event_name or not event_id:
        raise ValueError("Meta event must include event_name and event_id.")

    try:
        ConversionEventLog.objects.create(
            event_name=event_name,
            event_id=event_id,
            metadata=metadata or {},
        )
    except IntegrityError:
        logger.info(
            "Meta CAPI event already logged; skipping. event_name=%s event_id=%s",
            event_name,
            event_id,
        )
        return False

    logger.info(
        "Queued Meta CAPI event. event_name=%s event_id=%s",
        event_name,
        event_id,
    )
    send_meta_capi_events.delay([event], event_id=event_id)
    return True
