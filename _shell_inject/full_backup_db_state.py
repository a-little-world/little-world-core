from back.management import controller  # !dont_include
from back.management import random_test_users  # !dont_include
from back.management.models import User, Profile  # !dont_include
from back.management.models import rooms  # !dont_include
from back.emails import mails  # !dont_include
from django.apps import apps
from django.utils import timezone
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
import multiprocessing as mp
from itertools import repeat
import ctypes

import multiprocessing
import time
import random
from queue import Empty
import time

start = time.time()

output_dir = "./dumped_data"

output_dir_present = os.path.exists(output_dir)
if not output_dir_present:
    os.mkdir(output_dir)

os.chdir("./dumped_data")

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

ARCHIVE_OUTPUTS = True
ENCRYPT_OUTPUTS = True
DELETE_OUTPUTS = True
PROGRESS_FILE = True
PROCESS_OUTPUT = "./PROGRESS.dumpdata.json"
PROGRESS_OUTPUT = PROCESS_OUTPUT
ENCRYPTION_PASSWORD = "Test123"
CONCURRENT_DUMPS = 4

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

def write_progress(data):
    """
    Function to write progress into a JSON file.
    :param data: The data that will be written into the JSON file.
    """
    with open(PROGRESS_OUTPUT, "w") as f:
        json.dump(data, f, indent=2)

def read_progress():
    """
    Function to read any pre-existing progress from a JSON file.
    :return processed_data: The data previously saved in the JSON file.
    """
    try:
        with open(PROGRESS_OUTPUT, 'r') as f:
            processed_data = json.load(f)
    except FileNotFoundError:
        processed_data = {"config": {"MODELS": [], "ENCRYPTED_FILES": []},"progress": []}

    return processed_data


def extract_model_data(app, model, lock, process_no, models_extracted,errors, progress_data, models_list, encrypted_files_list):

    # Initiate error_occured to keep track if an extraction results in any error
    global error_occured
    model_path = f"{model}"
    error_occured = False
    

    try:
        # Add model to MODELS
        models_list.append(model)
        total_amount = apps.get_model(app_label=model.split(".")[0], model_name=model.split(".")[-1]).objects.all().count()
        print("Total amount of objects:", total_amount)

        # Actual extraction
        call_command('dumpdata', '-o', f'{model_path}.json', '-v', '3', '--indent', '2', model)

        output_size = get_size(f"{model_path}.json", unit='mb')
        print("File size:", output_size, "mb")
        
        
        if PROGRESS_FILE:
            out_file_path = f"{model_path}.json"
            progress_data.append({
                "model": model, 
                "step": "dumpdata",
                "total": total_amount, 
                "path": out_file_path,
                "hash": calc_hash(out_file_path),
                "size": output_size,
                "time_stamp": str(timezone.now())
            })

        # Implementing zipping and compression
        if ARCHIVE_OUTPUTS:
            print("Preparing to compress file: ", f"{model_path}.json")
            shutil.make_archive(f"{model_path}.compressed", 'zip', base_dir=f"{model_path}.json")

            output_size = get_size(f"{model_path}.json", unit='mb')
            print("File size:", output_size, "mb")

            if PROGRESS_FILE:
                out_file_path = f"{model_path}.compressed.zip"
                output_size = get_size(out_file_path, unit='mb')
                progress_data.append({
                    "model": model, 
                    "step": "compress",
                    "total": total_amount, 
                    "path": out_file_path,
                    "hash": calc_hash(out_file_path),
                    "size": output_size,
                    "time_stamp": str(timezone.now())
                })

            if ENCRYPT_OUTPUTS:
                print("Preparing to encrypt file: ", f"{model_path}.compressed.zip")

                encrypt_and_write(ENCRYPTION_PASSWORD, f"{model_path}.compressed.zip", f"{model_path}.compressed.encrypted")
                out_file_path = f"{model_path}.compressed.encrypted"
                output_size = get_size(out_file_path, unit='mb')

                print("File size:", output_size, "mb")

                if PROGRESS_FILE:
                    encrypted_files_list.append(f"{model_path}.compressed.encrypted")
                    progress_data.append({
                        "model": model,
                        "step": "encrypt",
                        "total": total_amount,
                        "path": out_file_path,
                        "hash": calc_hash(out_file_path),
                        "size": output_size,
                        "time_stamp": str(timezone.now())
                    })
                if DELETE_OUTPUTS:
                    assert ARCHIVE_OUTPUTS and ENCRYPT_OUTPUTS, "DELETE_OUTPUTS requires ARCHIVE_OUTPUTS and ENCRYPT_OUTPUTS to be True"
                    os.remove(f"{model_path}.json")
                    os.remove(f"{model_path}.compressed.zip")

                    if PROGRESS_FILE:
                        progress_data.append({
                            "model": model,
                            "step": "delete_files",
                            "time_stamp": str(timezone.now())
                        })
                        
        print(f"({models_extracted.value}/{models_to_extract}) [errors: {errors.value}] finished processing model:", model)    

    except Exception as e:
        error_msg = f'Error processing model: {model} to file: {model_path}.json, error: {e}'
        print(error_msg)
        error_occured = True
        if PROGRESS_FILE:
            progress_data.append({
                "model": model,
                "step": "error",
                "error": error_msg,
            })

    # Lock before changing any shared variables across processes
    lock.acquire()
    try:
        models_extracted.value += 1
        print(f"\t- Process {process_no}> finished processing model:", model)

        if error_occured:
            errors.value += 1

        # Updating the progress file with updated progress_data
        if PROGRESS_FILE:
            
            PROGRESS_DATA = read_progress()
            PROGRESS_DATA["config"]["MODELS"] = list(models_list)
            PROGRESS_DATA["config"]["ENCRYPTED_FILES"] = list(encrypted_files_list)
            PROGRESS_DATA["progress"] = list(progress_data)
            write_progress(PROGRESS_DATA)

    finally:
        lock.release()   

with multiprocessing.Manager() as manager:
    lock = multiprocessing.Lock()
    models_extracted = manager.Value('i', 0)
    errors = manager.Value('i', 0)
    progress_data = manager.list()
    models_list = manager.list()
    encrypted_files_list = manager.list()

    processes = []

    # for app in ["management"]:
    #    for model in ["management.User"]:
    for app in models_per_app:
        for model in models_per_app[app]:
            process = multiprocessing.Process(
                target=extract_model_data, 
                args=(
                    app, 
                    model, 
                    lock,
                    len(processes) + 1,
                    models_extracted,
                    errors,
                    progress_data,
                    models_list,
                    encrypted_files_list,
                )
            )
            processes.append(process)
            process.start()

    for process in processes:
        process.join()
    print("\nData dumping completed with", errors.value, "errors")
    print("A total of", models_extracted.value, "models were extracted")



end = time.time()
time_diff = end - start
minutes = time_diff / 60.0

print(f"Time taken: {minutes} minutes")
if PROGRESS_FILE:
    
    PROGRESS_DATA = read_progress()
    PROGRESS_DATA["progress"].append({
        "step": "finished",
        "time_stamp": str(timezone.now()),
        "duration_minutes": minutes,
    })
    write_progress(PROGRESS_DATA)