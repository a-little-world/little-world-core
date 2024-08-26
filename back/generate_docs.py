import os
import django
from pdoc import pdoc, render
from pathlib import Path


render.configure(template_directory="/back/docs_template", include_undocumented=True)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "back.settings")
django.setup()

if __name__ == "__main__":
    output_directory = Path("/tmp/html")
    modules_to_document = ["back", "management", "emails"]  # Replace with your actual module(s)

    pdoc(*modules_to_document, output_directory=output_directory)
