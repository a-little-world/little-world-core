from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails import mails  # !dont_include
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile
# !include from emails import mails
from datetime import date
from django.core.management import call_command
from django.apps import apps
from contextlib import redirect_stdout



app_models = apps.get_app_config('management').get_models()

apps_to_process = 0
models_to_extract = 0

models_per_app = {}

print("MODELS", apps.get_models())

def fullname(o):
    module = o.__class__.__module__
    if module is None or module == str.__class__.__module__:
        return o.__class__.__name__
    return module + '.' + o.__class__.__name__

for app in apps.get_app_configs():
    #print("APP", app.name, ":")
    app_name = app.name
    short_app_name = app_name.split(".")[-1]
    app_models = app.get_models()
    apps_to_process += 1

    for model in app_models:
        models_to_extract += 1
        if not app.verbose_name in models_per_app:
            models_per_app[app.verbose_name] = []
        #print("\tMODEL", model)
        model_spec = (f".".join([model.__module__, model.__name__])).split(".")
        models_per_app[app.verbose_name].append(short_app_name + "." + model_spec[-1])
        #print("\tSPEC", short_app_name + "." + model_spec[-1])

        #print("\t", model)
print(f"Total of {apps_to_process} apps to process with a total of {models_to_extract} models to extract.")

models_extracted = 0
for app in models_per_app:
    print("Extracting models for app:", app)
    for model in models_per_app[app]:
        print("Extracting model:", model)

        with open(f'{model}.json', 'w') as f:
            with redirect_stdout(f):
                call_command('dumpdata', '-v', '3', 'contenttypes.ContentType')
                
        print("Extracted model:", model, "to file:", f"{model}.json")
        
        # Move the file from the mounted container to the host then compress it
        print("Preparing to compress file: ", f"{model}.json")
        # TODO: compress then encrypt