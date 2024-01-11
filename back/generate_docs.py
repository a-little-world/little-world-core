import os
import django
import subprocess
import sys

additional_paths = [
    "/back/back",
    "/usr/local/lib/python3.11/site-packages",
    "/back",
    "/back/management",
    "/back/front",
    "/back/tracking",
    "/back/emails",
]

if __name__ == "__main__":

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'back.settings')

    # Extend the PYTHONPATH with your additional paths
    python_path = os.environ.get('PYTHONPATH', '')
    extended_python_path = os.pathsep.join(additional_paths) + os.pathsep + python_path
    os.environ['PYTHONPATH'] = extended_python_path
    
    print("PYTHONPATH:", os.environ['PYTHONPATH'])

    # Initialize Django
    django.setup()

    # Call pdoc CLI with the arguments to generate the documentation
    subprocess.run(["pdoc", "-o", "/tmp/html", "back"])