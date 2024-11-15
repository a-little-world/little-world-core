import sys
import csv

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
    "contact_second_name",
    "contact_phone",
    "website_url",
    "extra__submitted_at",
    "extra__token"
]

# 1 - parse csv
csv_file = sys.argv[1]
results = []

lines = []

with open(csv_file) as csvfile:
    reader = csv.reader(csvfile, quoting=csv.QUOTE_STRINGS)
    for row in reader:
        lines.append(row)
    
    
print(lines[2])

# 2 - create json
json_data = {}
for i, row in enumerate(lines[1:]):
    json_data[i] = {}
    for j, cell in enumerate(row):
        if j >= len(HEADERS):
            print(f" outbounds i: {i}, j: {j}, cell: {cell}")
            break
        json_data[i][HEADERS[j]] = cell
        
target_groups_map = {
    "Einzelpersonen": "individual",
    "Kinder": "child",
    "Familien": "family",
    "Familie": "family",
    "Schüler:innen": "student",
    "Paare": "individual",
    "Jugendliche": "adolescent",
    "Student:innen": "student",
    "Senior:innen": "senior",
    "geflüchtete Menschen": "error",
    "Wirtschaftsunternehmen": "error",
    "Jugendliche/junge Erwachsene": "adolescent",
    "Freund*innen": "error",
    "Vermitteln an Patenschaftsorganisationen": "error",
    "": "error"
}
        
# 3 - parse to db format
for i in json_data:
    num = int(i)
    for j, v in json_data[i].items():
        # TODO: add more cheks and conversions
        if j == "target_groups":
            try:
                target_groups = v.split(",")
                for k, target_group in enumerate(target_groups):
                    target_groups[k] = target_groups_map[target_group.strip()]
                    if target_groups[k] != "" and target_groups[k] != "error":
                        json_data[i][j] = target_groups
            except Exception as e:
                print(f"error at {str(e)}")
                
print(json_data[1])