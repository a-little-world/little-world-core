import csv
import json

from django.core.management.base import BaseCommand
from patenmatch.api import PatenmatchOrganizationSerializer
from patenmatch.models import SupportGroups


class Command(BaseCommand):
    def add_arguments(self, parser):
        # Positional arguments
        parser.add_argument("arg1", type=str, help="User hash")

    def handle(self, **options):
        # PatenmatchOrganization.objects.all().delete()

        HEADERS = [
            "name",
            "target_groups",
            "extra__is_buddy_programm",
            "postal_code",
            "contact_email",
            "maximum_distance",
            "extra__adress",
            "extra__how_many_buddies",
            "contact_first_name",
            "contact_phone",
            "website_url",
            "extra__submitted_at",
            "extra__token",
        ]

        # 1 - parse csv
        csv_file = options["arg1"]
        results = []

        lines = []

        with open(csv_file) as csvfile:
            reader = csv.reader(csvfile, quoting=csv.QUOTE_ALL)
            for row in reader:
                lines.append(row)

        # print(lines[2])

        # 2 - create json
        json_data = {}
        for i, row in enumerate(lines[1:]):
            json_data[i] = {}
            for j, cell in enumerate(row):
                if j >= len(HEADERS):
                    print(f" outbounds i: {i}, j: {j}, cell: {cell}")
                    break
                json_data[i][HEADERS[j]] = cell
            names = json_data[i]["contact_first_name"].split(" ")
            json_data[i]["contact_second_name"] = names[-1]
            json_data[i]["contact_first_name"] = names[0].replace(",", "").replace(".", "")

        target_groups_map = {
            "Einzelpersonen": SupportGroups.INDIVIDUAL,
            "Kinder": SupportGroups.CHILD,
            "Familien": SupportGroups.FAMILY,
            "Familie": SupportGroups.FAMILY,
            "Schüler:innen": SupportGroups.STUDENT,
            "Paare": "individual",
            "Jugendliche": SupportGroups.ADOLESCENT,
            "Student:innen": SupportGroups.STUDENT,
            "Senior:innen": SupportGroups.SENIOR,
            "geflüchtete Menschen": SupportGroups.ERROR,
            "Wirtschaftsunternehmen": SupportGroups.ERROR,
            "Jugendliche/junge Erwachsene": SupportGroups.ADOLESCENT,
            "Freund*innen": SupportGroups.ERROR,
            "Vermitteln an Patenschaftsorganisationen": SupportGroups.ERROR,
            "": SupportGroups.ERROR,
        }

        # 3 - parse to db format
        for i in json_data:
            for key, value in json_data[i].items():
                # TODO: add more cheks and conversions
                if key == "target_groups":
                    try:
                        target_groups = value.split(",")
                        for k, target_group in enumerate(target_groups):
                            target_groups[k] = target_groups_map[target_group.strip()]
                            if target_groups[k] != "" and target_groups[k] != "error":
                                json_data[i][key] = target_groups
                    except Exception as e:
                        print(f"error at {str(e)}")

        errors = []
        for jd in json_data:
            serializer = PatenmatchOrganizationSerializer(data=json_data[jd])
            if not serializer.is_valid():
                errors.append({"row": jd, "errors": serializer.errors})
            else:
                serializer.save()

        json_formatted_str = json.dumps(errors, indent=2)

        print(json_formatted_str)
