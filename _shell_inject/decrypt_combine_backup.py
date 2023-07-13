import glob
import base64
import sys
import shutil
import subprocess
subprocess.run("pip3 install ijson",shell=True)
subprocess.run("pip3 install pycryptodome",shell=True)
import ijson
from ijson.common import items
from django.core.serializers.json import DjangoJSONEncoder
import json
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto import Random

import os
os.chdir("./dumped_data")


def decrypt(key, source, decode=True):
    if decode:
        source = base64.b64decode(source.encode("latin-1"))
    # use SHA-256 over our key to get a proper-sized AES key
    key = SHA256.new(key).digest()
    IV = source[:AES.block_size]  # extract the IV from the beginning
    decryptor = AES.new(key, AES.MODE_CBC, IV)
    data = decryptor.decrypt(source[AES.block_size:])  # decrypt
    # pick the padding value from the end; Python 2.x: ord(data[-1])
    padding = data[-1]
    # Python 2.x: chr(padding) * padding
    if data[-padding:] != bytes([padding]) * padding:
        raise ValueError("Invalid padding...")
    return data[:-padding]  # remove the padding


def decrypt_write(password, filename, data, end=""):

    with open(filename, "rb") as f:
        data = f.read()
        decrypted = decrypt(bytes(password, "utf-8"), data, False)

    with open(f"{filename}{end}", "wb") as f:
        f.write(decrypted)
        f.close()

COMBINE = False
COMBINED_OUTPUT_FILE = "ALL.json"
PASSWORD = "Test123"

if COMBINE:
    with open(COMBINED_OUTPUT_FILE, "a") as f:
        f.write("[\n")

backup_files = glob.glob("*.compressed.encrypted")
amound_files = len(backup_files)
                
print(f"Found {amound_files} encrypted backup files.)")

i = 0
total_lines = 0

for file_name in backup_files:
                
    print(f"Decrypting & writing file {i}/{amound_files}): " + file_name)

    decrypt_write(PASSWORD, file_name, None, end=".zip")
    final_file_name = file_name.replace(".compressed.encrypted", ".json")
    shutil.unpack_archive(f"{file_name}.zip", final_file_name)
    
    if COMBINE:
        with open(COMBINED_OUTPUT_FILE, "a") as f:
            with open(f"{final_file_name}/{final_file_name}", "r") as f2:
                for record in ijson.items(f2, prefix="item"):
                    total_lines += 1
                    f.write(json.dumps(record, cls=DjangoJSONEncoder) + "," + "\n")
    i += 1

if COMBINE:
    with open(COMBINED_OUTPUT_FILE, "a") as f:
        f.write("]")
    
with open("DECRYPTION_SUMMARY.json", "w+") as fs:
    fs.write(json.dumps({
        "amount_of_lines": total_lines
    }))


print("completed! total lines: " + str(i))