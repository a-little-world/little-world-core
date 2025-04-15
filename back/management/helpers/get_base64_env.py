import base64
import json
import os


def get_base64_env(env_name):
    try:
        # base64.b64encode(json.dumps(creds).encode("utf-8")).decode("utf-8")
        # "e30=" is base64 for "{}"
        return json.loads(base64.b64decode(os.environ.get(env_name, "e30=")))
    except Exception:
        return {}
