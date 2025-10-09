from celery import shared_task

from video.services.livekit_session_correction import process_unusually_long_sessions


@shared_task(name="video.tasks.daily_fix_unusually_long_livekit_sessions")
def daily_fix_unusually_long_livekit_sessions(cutoff_hours: float = 4.0):
    """
    Runs daily to cap unusually long sessions for records aged between 24 and 60 hours.
    """
    # 24h <= age < 60h window
    result = process_unusually_long_sessions(
        cutoff_hours=cutoff_hours,
        min_age_hours=24.0,
        max_age_hours=60.0,
        dry_run=False,
    )
    return result


