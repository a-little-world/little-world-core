from patenmatch.models import PatenmatchOrganization
import pgeocode
import random

nomi = pgeocode.Nominatim("de")
postal_codes = nomi.query_postal_code(nomi._data["postal_code"].unique())
postal_codes = postal_codes.dropna(subset=["postal_code"])


def get_random_postal_code(postal_codes):
    random_postal_code = random.choice(postal_codes["postal_code"].tolist())

    return random_postal_code


instances = []
for i in range(1, 1000):
    instance = PatenmatchOrganization(name="test_" + str(i), postal_code=str(get_random_postal_code(postal_codes)), contact_first_name="test_first_name", contact_second_name="test_second_name", contact_email="blabla" + str(i) + "@test.de")
    instances.append(instance)

if instances:
    PatenmatchOrganization.objects.bulk_create(instances)
