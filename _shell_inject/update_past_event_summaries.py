from management.tasks import write_hourly_backend_event_summary
from tracking.models import Summaries
from datetime import datetime, timedelta, timezone
import json
# send_new_message_notifications_all_users(
#    filter_out_base_user_messages=True,
#    do_send_emails=False,
#    do_write_new_state_to_db=True,
#    send_only_if_logged_in_withing_last_3_weeks=False
# )

# First backend event ever tracked was at
#
from django_celery_results.models import TaskResult

first_event_logged_time = datetime(
    2022, 12, 19, 5, 18, 11, 931582, tzinfo=timezone.utc)

ONE_HOUR = timedelta(hours=1)
NOW = datetime.now()


hourly_summaries = Summaries.objects.filter(label="hourly-event-summary")


def does_event_summary_exist(hour):
    this_hour = hour.replace(minute=0, second=0, microsecond=0)
    hourly_summaries.filter(f"hour-{this_hour}")
    return hourly_summaries.exists()


def calculate_for_all_past_hours():

    cur_check_time = first_event_logged_time

    limit = 10

    while (cur_check_time + ONE_HOUR) < NOW:
        if limit is not None:
            limit -= 1
            if limit <= 0:
                print("Limit reached stopped caculating")
                break
        print("Checking for ", str(cur_check_time))
        # check inside of celery results if that hours event summary already exists
        if does_event_summary_exist(cur_check_time):
            print("Summary appears to already exist")
        else:
            print("GENERATE")
            # write_hourly_backend_event_summary.delay(
            #    start_time=str(cur_check_time))


# def test():
#    now = datetime.now()
#    start = now - timedelta(hours=40)
#    end = now - timedelta(hours=10)
#    out = write_hourly_backend_event_summary(
#        start_time=str(start), end_time=str(end))
#    print(json.dumps(out, indent=4))
