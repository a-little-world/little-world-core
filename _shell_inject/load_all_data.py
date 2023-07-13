from django.core.management import call_command
import subprocess
subprocess.run("pip3 install ijson",shell=True)
import ijson
import os
import json
from django.core.serializers.json import DjangoJSONEncoder
from django.core.management import call_command


os.chdir("./dumped_data")

with open("DECRYPTION_SUMMARY.json", "r") as f:
    summary = json.load(f)
    
total_lines = summary["amount_of_lines"]
    

MODELS = [
  "tracking.Event",
  "tracking.Summaries",
  "tracking.GraphModel",
  "emails.EmailLog",
  "cookie_consent.CookieGroup",
  "cookie_consent.Cookie",
  "cookie_consent.LogItem",
  "management.User",
  "management.Profile",
  "management.ProfileAtMatchRequest",
  "management.Notification",
  "management.State",
  "management.EmailSettings",
  "management.Settings",
  "management.Room",
  "management.ScoreTableSource",
  "management.MatchinScore",
  "management.CommunityEvent",
  "management.BackendState",
  "management.NewsItem",
  "management.HelpMessage",
  "management.PastMatch",
  "management.TranslationLog",
  "management.UnconfirmedMatch",
  "management.NoLoginForm",
  "management.StillInContactForm",
  "management.Match",
  "django_private_chat2.UploadedFile",
  "django_private_chat2.DialogsModel",
  "django_private_chat2.MessageModel",
  "django_rest_passwordreset.ResetPasswordToken",
  "django_celery_beat.SolarSchedule",
  "django_celery_beat.IntervalSchedule",
  "django_celery_beat.ClockedSchedule",
  "django_celery_beat.CrontabSchedule",
  "django_celery_beat.PeriodicTasks",
  "django_celery_beat.PeriodicTask",
  "django_celery_results.TaskResult",
  "django_celery_results.ChordCounter",
  "django_celery_results.GroupResult",
  "admin.LogEntry",
  "auth.Permission",
  "auth.Group",
  "contenttypes.ContentType",
  "sessions.Session"
]


# we load the data in batches otherwise this would cause ooms
for model in MODELS:
    i = 0
    batch = 0
    LINES_PER_BATCH = 1

    with open(f"{model}.json/{model}.json", "r") as f2:
        for line in ijson.items(f2, 'item'):
            print(f"Loading data line ({i}/{total_lines})")
            print(line)
            
            batch_file = f"./batch_{model}_{batch}.json"
            
            if i % LINES_PER_BATCH == 0:
                with open(batch_file, "w+") as f3:
                    f3.write("[\n")

            closing_line = ((i % LINES_PER_BATCH) == (LINES_PER_BATCH -1) ) or (LINES_PER_BATCH == 1) or (i == total_lines - 1)

            with open(batch_file, "a") as f3:
                f3.write(json.dumps(line, cls=DjangoJSONEncoder))
                if not closing_line:
                    f3.write(",")
                f3.write("\n")
            
            if closing_line:
                print("Loading batch ({batch}/{total_batches})".format(batch=batch, total_batches=total_lines/LINES_PER_BATCH))
                with open(batch_file, "a") as f3:
                    f3.write("]")
                batch += 1
                call_command('loaddata', batch_file, '-v', '3', '-i')
                os.remove(batch_file)
            i += 1
        


