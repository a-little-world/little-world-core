from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails import mails  # !dont_include
from django.apps import apps
import shutil
import json
import os
import subprocess
# !include from management.models import rooms
# !include from management import controller
# !include from management import random_test_users
# !include from management.models import User, Profile
# !include from emails import mails
subprocess.run("pip3 install pycryptodome",shell=True)
from datetime import date
from django.core.management import call_command
from django.apps import apps
from contextlib import redirect_stdout
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto import Random
import base64
import hashlib



app_models = apps.get_app_config('management').get_models()

apps_to_process = 0
models_to_extract = 0

models_per_app = {}

print("MODELS", apps.get_models())

def calc_hash(file_path, algorithm='sha256'):
    hash_algorithm = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096),b""):
            hash_algorithm.update(byte_block)
    return hash_algorithm.hexdigest()

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
output_dir = "./dumped_data"

output_dir_present = os.path.exists(output_dir)
if not output_dir_present:
    os.mkdir(output_dir)


models_extracted = 0
errors = 0

ARCHIVE_OUTPUTS = True
ENCRYPT_OUTPUTS = True
DELETE_OUTPUTS = False
PROGRESS_FILE = True
PROCESS_OUTPUT = "progress.dumpdata.json"
ENCRYPTION_PASSWORD = "Test123"

CONTINUE = False # to continue an aborted download

def encrypt(key, source, encode=True):
    # use SHA-256 over our key to get a proper-sized AES key
    key = SHA256.new(key).digest()
    IV = Random.new().read(AES.block_size)  # generate IV
    encryptor = AES.new(key, AES.MODE_CBC, IV)
    # calculate needed padding
    padding = AES.block_size - len(source) % AES.block_size
    # Python 2.x: source += chr(padding) * padding
    source += bytes([padding]) * padding
    # store the IV at the beginning and encrypt
    data = IV + encryptor.encrypt(source)
    return base64.b64encode(data).decode("latin-1") if encode else data


def encrypt_and_write(password, file_in, file_out):
    with open(file_in, "rb") as f:
        encrypted = encrypt(bytes(password, "utf-8"), f.read(), False)

    with open(file_out, "wb") as f:
        f.write(encrypted)
        f.close()

def get_size(file_path, unit='bytes'):
    file_size = os.path.getsize(file_path)
    exponents_map = {'bytes': 0, 'kb': 1, 'mb': 2, 'gb': 3}
    if unit not in exponents_map:
        raise ValueError("Must select from \
        ['bytes', 'kb', 'mb', 'gb']")
    else:
        size = file_size / 1024 ** exponents_map[unit]
        return round(size, 3)
    

PROGRESS_DATA = {"progress": [], "config": {
    "ARCHIVE_OUTPUTS": ARCHIVE_OUTPUTS,
    "ENCRYPT_OUTPUTS": ENCRYPT_OUTPUTS,
    "DELETE_OUTPUTS": DELETE_OUTPUTS,
    "PROGRESS_FILE": PROGRESS_FILE,
    "ENCRYPTION_PASSWORD": "hidden",
    "MODELS": [],
    "ENCRYPTED_FILES": [],
}}

def write_progress(data):
    with open(PROCESS_OUTPUT, "w") as f:
        json.dump(data, f, indent=2)

def read_progress():
    if os.path.exists(PROCESS_OUTPUT):
        with open(PROCESS_OUTPUT, "r") as f:
            return json.load(f)
    else:
        return PROGRESS_DATA

for app in models_per_app:
    print("Extracting models for app:", app)
    
    if PROGRESS_FILE:
        PROGRESS_DATA = read_progress()

    for model in reversed(models_per_app[app]):
        
        model_path = f"{output_dir}/{model}"
        
        if PROGRESS_FILE:
            PROGRESS_DATA["config"]["MODELS"].append(model)

        print("Extracting model:", model)
        try:
            total_amount = apps.get_model(app_label=model.split(".")[0], model_name=model.split(".")[-1]).objects.all().count()
            print("Total amount of objects:", total_amount)
            
            # TODO: if we compress then we prob don't want to indent
            call_command('dumpdata', '-o', f'{model_path}.json', '-v', '3', '--indent', '2', model)
                    
            print("Output model_path:", model_path, "to file:", f"{model_path}.json")
            models_extracted += 1
            
            output_size = get_size(f"{model_path}.json", unit='mb')
            print("File size:", output_size, "mb")
            
            if PROGRESS_FILE:
                out_file_path = f"{model_path}.json"
                PROGRESS_DATA["progress"].append({
                    "model": model, 
                    "step": "dumpdata",
                    "total": total_amount, 
                    "path": out_file_path,
                    "hash": calc_hash(out_file_path),
                    "size": output_size,
                })
                write_progress(PROGRESS_DATA)
            

            if ARCHIVE_OUTPUTS:
                print("Preparing to compress file: ", f"{model_path}.json")
                shutil.make_archive(f"{model_path}.compressed", 'zip', f"{model_path}.json")

                output_size = get_size(f"{model_path}.json", unit='mb')
                print("File size:", output_size, "mb")
                
                
                if PROGRESS_FILE:
                    out_file_path = f"{model_path}.compressed.zip"
                    PROGRESS_DATA["progress"].append({
                        "model": model, 
                        "step": "compress",
                        "total": total_amount, 
                        "path": out_file_path,
                        "hash": calc_hash(out_file_path),
                        "size": output_size,
                    })
                    write_progress(PROGRESS_DATA)
                
            if ENCRYPT_OUTPUTS:
                assert ARCHIVE_OUTPUTS, "ENCRYPT_OUTPUTS requires ARCHIVE_OUTPUTS to be True"
                print("Preparing to encrypt file: ", f"{model_path}.json")

                encrypt_and_write(ENCRYPTION_PASSWORD, f"{model_path}.compressed.zip", f"{model_path}.compressed.encrypted")

                output_size = get_size(f"{model_path}.json", unit='mb')
                print("File size:", output_size, "mb")

                if PROGRESS_FILE:
                    out_file_path = f"{model_path}.compressed.encrypted"
                    PROGRESS_DATA["config"]["ENCRYPTED_FILES"].append(f"{model_path}.compressed.encrypted")
                    PROGRESS_DATA["progress"].append({
                        "model": model, 
                        "step": "encrypt",
                        "total": total_amount, 
                        "path": out_file_path,
                        "hash": calc_hash(out_file_path),
                        "size": output_size,
                    })
                    write_progress(PROGRESS_DATA)
                
            if DELETE_OUTPUTS:
                assert ARCHIVE_OUTPUTS and ENCRYPT_OUTPUTS, "DELETE_OUTPUTS requires ARCHIVE_OUTPUTS and ENCRYPT_OUTPUTS to be True"
                os.remove(f"{model_path}.json")
                os.remove(f"{model_path}.compressed.zip")
                
                if PROGRESS_FILE:
                    PROGRESS_DATA["progress"].append({
                        "model": model, 
                        "step": "delete_files",
                    })
                    write_progress(PROGRESS_DATA)

        except Exception as e:
            
            error_msg = f"Error extracting model_path: {model_path} to file: {model_path}.json, error: {e}"
            
            with open(f"{model_path}.error", "w") as f:
                f.write(error_msg)

            print(error_msg)
            errors += 1
            if PROGRESS_FILE:
                PROGRESS_DATA["progress"].append({
                    "model": model, 
                    "step": "error_occured",
                    "error": error_msg,
                })
                write_progress(PROGRESS_DATA)
        print(f"({models_extracted}/{models_to_extract}) [errors: {errors}] finished processing model:", model)