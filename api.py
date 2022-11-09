"""
This is a test helper and admin tool to remulate api calls
how it works:
1 - fetch the api shema from /api/schema ( or provide it from file )
2 - authenticate a virtual session with admin credentials
3 - make api call with a simple auto generated syntax

e.g.:
./api.py [method] [fuzzy or exact path] --url [url] --json [json-input] --json-file [json-file-input] -p was=nope <-- any number of parameter inputs
./api.py get getuser -> would fuzzy evalute getuser to /api/v1/admin/getuser/

"""
import argparse
import os

DEF_ADMIN_PW = "AdminTest123!"
DEF_ADMIN_EMAIL = "admin@little-world.com"
DEF_URL = "localhost:8000"

methods = ["get", "post", "list"]


def _params():
    """
    Pro tip: you can use export ENV='' in the current shell to set ADMIN_PW etc...
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('method_search', metavar='A', type=str,
                        default=["get", "self"], nargs='2',
                        help="methods, one of: " + ", ".join(methods) + " and a fuzzy search path")
    parser.add_argument('-u', '--url',
                        help="The url we should fetch the shema from ( maybe overwriten by --schema )")
    parser.add_argument('-s', '--schema',
                        help="If you want to provide a shema yaml file instead")
    parser.add_argument('-e', '--email',
                        help="Email of the user to authenticate")
    parser.add_argument('-pw', '--password',
                        help="Password of the user to authenticate")
    args = parser.parse_args()

    if not args.password:
        args.password = os.environ.get("LW_ADMIN_PW", DEF_ADMIN_PW)

    if not args.email:
        args.email = os.environ.get("LW_ADMIN_EMAIL", DEF_ADMIN_EMAIL)

    if not args.url:
        args.email = os.environ.get("LW_API_URL", DEF_URL)

    schema = None
    if not args.schema:
        schema = ""  # TODO: load the schema from file
    else:
        schema = ""  # TODO: fetch the schema from url
    assert schema

    # Load the schema ... TODO
