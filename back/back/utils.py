import random
from uuid import uuid4

VERSION = 1


def _api_url(slug, v=VERSION, admin=False):
    return f"api/admin/v{v}/{slug}/" if admin else f"api/v{v}/{slug}/"


def _double_uuid():
    return str(uuid4()) + "-" + str(uuid4())


def _rand_int6():
    return random.randint(100000, 999999)
