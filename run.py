#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

""" General entry point for backend build and deployment processes """
import shutil
from functools import partial, wraps
import contextlib
import os
import sys
import argparse
import signal
import json
from cli.tim_cli_utils import *
USE_BASH_AUTOMCOMPLETION = False
try:  # We don't make this required cause people might not use bash
    import argcomplete
    USE_BASH_AUTOMCOMPLETION = True
except:
    print('WARN: "argcomplete" import failed!, ' +
          'you have no sleek bash auto completion!\n' +
          'maybe try `pip3 install argcomplete`')

TAG = "littleworld_back"
FRONT_TAG = "littleworld_front"
PORT = 8000


class c:
    # Backend container stuff
    dbuild = ["docker", "build"]
    drun = ["docker", "run"]
    file = ["-f", "Dockerfile.dev"]
    dtag = f"{TAG}.dev"
    ptag = f"{TAG}.prod"
    port = ["-p", f"{PORT}:8000"]
    vmount = [
        "-v", f"{os.getcwd()}/back:/back",
        "-v", f"{os.getcwd()}/front:/front"]
    host_routes = ["--add-host=host.docker.internal:host-gateway"]
    denv = ["--env-file", "./env"]
    penv = ["--env-file", "./penv"]
    shell = "sh"
    redis_port = ["-p", "6379:6379"]
    redis_name = ["--name", "little-world-redis"]

    # Frontend container stuff
    front_docker_file = ["-f", "Dockerfile.front"]
    vmount_front = [
        "-v", f"{os.getcwd()}/front:/front",
        # We mount also the backend, so static files can be copied over
        "-v", f"{os.getcwd()}/back:/back"
    ]
    front_tag = f"{FRONT_TAG}.dev"

    # For making the spinix docs
    vmount_spinix = ["-v", f"{os.getcwd()}/_docs:/docs",
                     "-v", f"{os.getcwd()}/back:/docs_source/backend"]
    file_spinix = ["-f", "Dockerfile.docs"]
    tag_spinix = "docs.spinix"

    # Staging server
    file_staging = ["-f", "Dockerfile.stage"]
    staging_tag = f"{TAG}.stage"
    stage_env = "./env_stage"

    staging_keys = "staging/staging_keys.kdbx"
    staging_key_file = "staging/little-world-staging-key.key"


subprocess_capture_out = {
    "capture_output": True,
    "text": True
}


def _parser(use_choices=False):
    """
    Commandline args:
    most notably 'actions'
        the default ( -> `./run.py` ) is configured for development to run the following steps
        1. Build docker image ( required for all the following steps)
        2. static extraction
        3. mirations for the db
        4. running the container interactively ( close with ctl-C )

    We use choices only for autocompletion, otherwise they can cause issue with actions that parse their own args
    """

    possible_actions = get_all_action_aliases()
    possible_actions.append("")  # Empty action
    default_actions = ["_setup", "build", "static", "migrate", "run"]
    parser = argparse.ArgumentParser()
    parser.add_argument('actions', metavar='A', type=str, default="" if use_choices else default_actions,
                        **(dict(choices=possible_actions) if use_choices else {}), nargs='*', help='action')
    parser.add_argument('-b', '--btype', default="dev",
                        help="prod, dev, any", **(dict(choices=["development", "staging", "deployment"]) if use_choices else {}))
    parser.add_argument('-bg', '--background',
                        action="store_true", help="Run the docker container in background (`./run.py kill` to stop)")
    parser.add_argument(
        '-o', '--output', help="Ouput file or path required by some actions")
    parser.add_argument(
        '-i', '--input', help="Input file (or data) required by some actions")
    parser.add_argument('-sa', '--single-action', type=str,
                        **(dict(choices=get_all_full_action_names()) if use_choices else {}), help='action')

    # default actions required by tim_cli_utils (TODO: they should be moved there)
    parser.add_argument('-s', '--silent', action="store_true",
                        help="Mute all output exept what is required")

    return parser


def _env_as_dict(path: str) -> dict:
    with open(path, 'r') as f:
        return dict(tuple(line.replace('\n', '').split('=')) for line
                    in f.readlines() if not line.startswith('#'))


def _is_dev(a):
    return "dev" in a.btype


@register_action(name="setup_repos_containers", alias=["update", "_setup"], cont=True)
def _setup(args):
    """
    # If you clone this repo with: `git clone --recurse-submodules -j8 git://github.com/foo/bar.git` there is no need to install submodules
    setups up the whole installation:
    - clone all submodules
    - build frontend containers ( so basicly npm install all the packages in there )
    - load default database fixture TODO

    Generaly this has to be done only once, you can re-invoke this by running 'update' or delete `.run.py.setup_complete`
    """
    from datetime import datetime
    complete_file = ".run.py.setup_complete"
    # TODO: we want to skip frontend builds when running on github actions!
    if not os.path.exists(complete_file) or ["update"] in args.actions:
        _cmd = ["git", "submodule", "update", "--init", "--recursive"]
        subprocess.run(_cmd)

        build_front(args)

        with open(complete_file, "w") as file:
            file.write(datetime.now().strftime("%m/%d/%Y, %H:%M:%S"))
    else:
        print("Setup already run! If you want to updated submodules or frontend packages run ./run.py update")


@register_action(name="list_running", alias=["ps"])
def _list_running_instances(args):
    all_running = []

    # We mostry reference by tag
    for tag in [c.ptag, c.dtag, c.front_tag, c.staging_tag]:
        ps = _running_instances(tag)
        all_running += ps if isinstance(ps, list) else [ps]

    # Sometimes we like to use names, e.g.: redis
    # ( we can't tag cause this aint our image )
    for name in [c.redis_name[1]]:
        ps = _running_instances_name(name)
        all_running += ps if isinstance(ps, list) else [ps]

    print(all_running)

    return all_running


def _all_running():
    _cmd = ["docker", "ps", "--format",
            r"""{"ID":"{{ .ID }}", "Image": "{{ .Image }}", "Names":"{{ .Names }}"}"""]
    out = str(subprocess.run(_cmd, **subprocess_capture_out).stdout)
    return [eval(x) for x in out.split("\n") if x.strip()]


def _running_instances_name(name):
    ps = _all_running()
    return [x for x in ps if name in x["Names"]]


def _running_instances(tag=TAG):
    """ Get a list of running instance for docker 'tag' """
    ps = _all_running()
    return [x for x in ps if tag in x["Image"]]


def _docker_images(repo=TAG, tag=None):
    """ Runins a list of docke images filtered by 'repo' """
    _cmd = ["docker", "images", "--format", '"{{json . }}"']
    out = str(subprocess.run(_cmd, **subprocess_capture_out).stdout)
    images = [eval(x[1:-1]) for x in out.split("\n") if x.strip()]
    _filtered_images = []
    for img in images:
        repo_cond = repo in img['Repository']
        tag_cond = tag is None or tag in img['Tag']
        if all([repo_cond, tag_cond]):
            _filtered_images.append(img)
    return _filtered_images


@register_action(alias=["fg"])
def attach(args):
    """ Attach to running container instances """
    ps = _list_running_instances(args)
    # v-- we generaly only every want to attach to a backend
    ps = [p for p in ps if '_back' in p['Image']]
    assert len(ps) == 1, "where to attach? please specify -i " + \
        "\"{'ID':'...'}\""
    subprocess.run(["docker", "container", "attach", ps[0]["ID"]
                   if len(ps) == 1 else eval(args.input)["ID"]])


@register_action(cont=True, alias=["k"])
def kill(args, front=True, back=True, redis=True):
    """ Kills all the running container instances (back & front)"""
    # TODO: this should also kill the lw redis instance ( if running )
    for tag in [c.front_tag if front else None,
                c.dtag if back else None,
                c.ptag if not _is_dev(args) else None]:
        if tag:
            _kill_tag(tag)

    for name in [c.redis_name[1] if redis else None]:
        if name:
            _kill_name(name)


def _kill_name(name):
    ps = _running_instances_name(name)
    _cmd = ["docker", "kill"]
    for p in ps:
        _c = _cmd + [p["ID"]]
        print(' '.join(_c))
        subprocess.run(_c)


def _kill_tag(tag):
    ps = _running_instances(tag)
    _cmd = ["docker", "kill"]
    for p in ps:
        _c = _cmd + [p["ID"]]
        print(' '.join(_c))
        subprocess.run(_c)


def _run_in_running(dev, commands, backend=True, capture_out=False, work_dir=None, fail=False):
    """
    Runns command in a running container.
    Per default this looks for a backend container.
    It will look for a frontend container with backend=False
    """
    return _run_in_running_tag(
        commands=commands,
        tag=(c.dtag if dev else c.ptag) if backend else FRONT_TAG,
        capture_out=capture_out,
        work_dir=work_dir, fail=fail)


def _run_in_running_tag(commands, tag, capture_out=False, work_dir=None, extra_docker_cmd=[], fail=False):
    """
    Runns command in a running container, with a specific tag
    """
    ps = _running_instances(tag)
    assert len(ps) > 0, "no running instances found"
    _cmd = ["docker", "exec",
            *(["-w", work_dir] if work_dir else []),
            *extra_docker_cmd, "-it", ps[0]["ID"], *commands]
    if not capture_out:
        subprocess.run(" ".join(_cmd), shell=True, check=fail)
    else:
        return str(subprocess.run(_cmd, **subprocess_capture_out).stdout)


@register_action(alias=["s", "sh", "$"])
def shell(args):
    """ Run a shell on a running container instance """
    _run_in_running(_is_dev(args), [c.shell])


@register_action(alias=["dump", "backup"])
def dumpdata(args):
    """ Creates a full database fixture """
    assert _is_dev(args), "Dumping data only allowed in dev"
    output = []
    if not args.output:
        print("No '-o' output specified, dumping to stdout")
    else:
        output = ["--output", args.output]
    _run_in_running(_is_dev(args), ["python3", "manage.py",
                    "dumpdata", *(["--indent", "2"] if not args.output else []), *output])


@register_action(alias=["load", "db_init"])
def loaddata(args):
    """ Load data from fixture """
    assert _is_dev(args), "Loading fixture data is only allowed in dev"
    assert args.input, "Please provide '-i' input file"
    _run_in_running(_is_dev(args), ["python3", "manage.py",
                    "dumpdata", "-i", args.input])


@register_action(alias=["m"], cont=True)
def migrate(args, running=False):
    """
    Migrate db inside docker container
    you can call this in code with running=True and it will not start and kill the container
    """
    with _conditional_wrap(not running,  # If the containers isn't running we will have to start it
                           before=lambda: _run(_is_dev(args), background=True),
                           after=lambda: kill(args, front=False)):
        _run_in_running(_is_dev(args), ["python3", "manage.py",
                        "makemigrations"])
        _run_in_running(_is_dev(args), ["python3", "manage.py",
                        "migrate"])


def _build_file_tag(file, tag, build_context_path=".", context_dir="./back"):
    _cmd = [*c.dbuild, "-f", file, "-t", tag, context_dir]
    print(" ".join(_cmd))
    subprocess.run(_cmd)


@register_action(alias=["set_root_pw"])
def _set_root_pw(args):
    """ Can be used to create the default root user in development """
    _make_root_user(**{
        "password": "password",
        "username": "username",
        "email": "username@mail.com",
        "tag": c.dtag
    })


def _make_root_user(password, username, email, tag=c.dtag):
    _run_in_running_tag(tag=tag, commands=[
                        "python3", "manage.py", "createsuperuser", "--no-input",
                        "--username", username,
                        "--email", email,
                        ], extra_docker_cmd=["-e", f"DJANGO_SUPERUSER_PASSWORD={password}"])


@register_action(alias=["stage"])
def deploy_staging(args):
    """
    Build and push the dockerfile for the staging server
    This acction requires some config params passed via -i
    optional 'ROOT_USER_PASSWORD' if passed will create a root user
    optional 'ROOT_USER_EMAIL', 'ROOT_USER_USERNAME'
    optional 'DOCS', default: False
    Note: pushing the image will only work if you have acess permission to the registry, ask tim@timschupp.de for that
    """
    assert args.input, " '-i' required, e.g.: \"{'AWS_ACCOUNT_ID':'...','AWS_REGISTRY_NAME':'...','AWS_REGION':''}\""
    aws_env = eval(args.input)
    args.input = None  # set to none now so no other actions use the parameter
    if 'DOCS' in aws_env and aws_env['DOCS'].lower() in ('true', '1', 't'):
        # Also build the documentation and move it to /static
        build_docs(args)
        # Copy the build files to
        shutil.copytree("./_docs/build/html", "./back/static/docs")
        # shutil.copytree("./docs", "./back/static/docs")
    # Build the frontends
    build_front(args)
    # Collect the statics ( also contains the files for open api specifications )
    build(args)  # Required build of the 'dev' image
    extract_static(args)
    # Build Dockerfile.stage
    _build_file_tag(c.file_staging[1], c.staging_tag, context_dir=".")
    if 'ROOT_USER_PASSWORD' in aws_env:
        print("Got 'ROOT_USER_PASSWORD' adding root user ...")
        # Ok in that case we create a base root user
        # The default staging deployment doesn't use *any* root user
        # This would only be needed if backend administration should be debugged in staging
        _run_tag_env(c.staging_tag, env=c.stage_env, background=True)
        assert 'ROOT_USER_USERNAME' in aws_env
        _make_root_user(**{
            "email": aws_env.get(
                "ROOT_USER_EMAIL", aws_env['ROOT_USER_USERNAME'] + "@mail.com"),
            "username": aws_env['ROOT_USER_USERNAME'],
            "password": aws_env['ROOT_USER_PASSWORD'],
            "tag": c.staging_tag
        })

    # Tag the image with the heroku repo, and push it:
    img = _docker_images(repo=c.staging_tag, tag="latest")
    print(img)
    assert len(img) == 1, \
        f"Multiple or no 'latest' image for name {c.staging_tag} found"
    aws_registry_url = f"{aws_env['AWS_ACCOUNT_ID']}.dkr.ecr.{aws_env['AWS_REGION']}.amazonaws.com/{aws_env['AWS_REGISTRY_NAME']}:latest"
    _cmd = ["docker", "tag", img[0]["ID"], aws_registry_url]
    print(" ".join(_cmd))
    subprocess.run(_cmd)
    _cmd = ["docker", "push", aws_registry_url]
    print(" ".join(_cmd))
    subprocess.run(_cmd)


@register_action(alias=["b"], cont=True)
def build(args):
    """
    Builds the docker container
    (if dev): uses the Dockerfile.dev
    """
    if not _is_dev(args):
        raise NotImplementedError

    # Note we only use build context in ./back this reduces our image by a fucking lot!
    # Otherwise we would have to specify .dockerignore for the specific images!
    _build_file_tag(c.file[1], c.dtag if _is_dev(
        args) else c.ptag, build_context_path="./back")


@register_action()
def open_staging_keys(args):
    """
    Opens the staging keys file, only pissible if you have the password *and* the keyfile for the staging env
    """
    print("W", "Attemping password read from `staging/staging_keys.kdbx` expecting password input:")
    _in = eval(args.input) if args.input else {}
    _cmd = ["keepass", c.staging_keys, "--keyfile",
            _in["keyfile"] if "keyfile" in _in else c.staging_key_file, "--pw-stdin",
            *(["--pw-stdin", _in["password"]] if "password" in _in else [])]
    subprocess.run(_cmd)


def _parse_keypass_password_info(out):
    lines = out.split("\n")
    keys = {}
    cur_key = None
    txt = ""
    for l in lines:
        if ":" in l and (not cur_key or not 'Notes' in cur_key):
            li = l.split(":")
            cur_key, txt = li
            keys[cur_key] = txt + "\n"
        else:
            if cur_key:
                keys[cur_key] += l + "\n"
    assert 'Password' in keys, "Password extraction failed, wrong credentials?"
    return keys


@register_action()
def unlock_and_write_staging_env(args):
    """
    Takes staging env file from the decrypted database and puts them into env_stage
    NOTE this requires keypassxc-cli!
    """
    import getpass
    _cmd = ["keepassxc-cli", "show", c.staging_keys,
            "ENV", "--k", c.staging_key_file]
    password = getpass.getpass()
    # print(password)
    out = subprocess.run(_cmd, stdout=subprocess.PIPE,
                         input=password,
                         encoding='ascii').stdout
    env_txt = _parse_keypass_password_info(out)["Notes"]
    print(env_txt)
    assert env_txt
    with open("env_stage", "w+") as f:
        f.write(env_txt)


@register_action(alias=["tests"], cont=True)
def run_django_tests(args):
    """
    Runs tests for all django apps in /back
    """
    _run_in_running(_is_dev(args), ["python3", "manage.py", "test"], fail=True)


@register_action(alias=["clear_static", "delte_static"], cont=True)
def delete_static_files(args, running=False):
    """
    Deltes everything in './back/static/*`
    sometimes required for cleaning up old static files!
    """
    print("Deleting static files")
    import glob
    for file in glob.glob("./back/static/*"):
        print(f"rm {file}")
        shutil.rmtree(file)
    print("Done")


@register_action(alias=["static", "collectstatic"], cont=True)
def extract_static(args, running=False):
    """
    This collects all the static files,
    this is especially imporant if you changed any files in django apps 'statics/*' directories!
    In production is would also automaticly upload the files to an S3 bucket! TODO
    """
    with _conditional_wrap(not running,  # If the containers isn't running we will have to start it
                           before=lambda: _run(_is_dev(args), background=True),
                           after=lambda: kill(args, front=False)):
        # '--noinput' why ask for overwrite permission we are in container anyways
        _run_in_running(_is_dev(args), ["python3", "manage.py",
                        "collectstatic", "--noinput"])


@register_action(alias=["makemessages"], cont=False, parse_own_args=True)
def make_messages(args, running=False):
    """
    Make translation messages for an specific app
    So this basicly scans a python app for _(), or gettext ...
    And creates accoring <app>/locale/<langs>/LC_MESSAGES/django.po
    (<langs>) is determined from back/back/settings.py
    """
    assert len(
        args.unknown) >= 1, "Provied <app> the app you want to make translation messages for"
    _run_in_running(_is_dev(args), [
                    "python3", "../manage.py", "makemessages", *(["-a"] if len(args.unknown) == 1 else [*args.unknown[1:]])], work_dir=f"/back/{args.unknown[0]}")
    import glob  # Yeah we require glob here but not to many people wanna make translations so not everybody needs this
    all_locale = [a for a in glob.glob(
        f"./back/{args.unknown[0]}/locale/*/*/*") if a.endswith(".po")]
    print("Updated: ", all_locale)
    # Now this smartly auto populates the 'tag' language
    # This will use pgettext(context, string) everywher where we wan't a context tag!
    # For all these translations we can auto detemine the 'tag'
    import polib  # Note if you don't need this step you can comment this out and wont be required to install polib
    import string
    for pofile in all_locale:
        if pofile.startswith(f"./back/{args.unknown[0]}/locale/tag"):
            print("Parsing: ", pofile)
            po = polib.pofile(pofile)
            valid_entries = [e for e in po if not e.obsolete]
            for entry in valid_entries:
                if hasattr(entry, "msgctxt") and entry.msgctxt is not None:
                    print(entry.msgctxt, entry.msgid, entry.msgstr)
                    # There might be python formaters in the string!
                    # We could ignore them, but I'll just patch them in!
                    format_opts = list(string.Formatter().parse(entry.msgid))
                    required_formatting = [
                        "{%s}" % arg for arg in format_opts[0][1:] if arg != "" and arg is not None] if format_opts else None
                    entry.msgstr = entry.msgctxt
                    if required_formatting:
                        entry.msgstr += "|" + ",".join(required_formatting)
                        pass
                    print("---> ", entry.msgctxt, entry.msgid, entry.msgstr)
            po.save()


@register_action(alias=["trans"], cont=True)
def translate(args, running=False):
    """
    This comiles the messages then extracts statics
    Basicly runs manage.py compilemessages
    We use '--use-fuzzy' by default, cause we wan't to easly change the english translation in code
    """
    _run_in_running(
        _is_dev(args), ["python3", "manage.py", "compilemessages", "--use-fuzzy"])
    extract_static(args, running=True)


@register_action(alias=["open_translation"], cont=True)
def open_trans(args):
    """
        Opens  atranslation file
        Expects -i <app-name>.<lang>
    """
    assert args.input
    app, lang = args.input.split(".")
    _cmd = ["code", "-r", f"./back/{app}/locale/{lang}/LC_MESSAGES/django.po"]
    subprocess.run(_cmd)


def _make_webpack_command(env, config, debug: bool, watch: bool):
    _cmd = [
        './node_modules/.bin/webpack',
        *(["--watch"] if watch else []),
        '--env', f'PUBLIC_PATH={env["WEBPACK_PUBLIC_PATH"]}',
        '--env', f'DEV_TOOL={env["WEBPACK_DEV_TOOL"]}',
        '--env', 'DEBUG=1' if debug else 'DEBUG=0',
        '--mode', 'development' if debug else 'production',
        '--config', config]
    return _cmd


@register_action(alias=["uf"], cont=True)
def update_front(args):
    """
    only to be run when frontends are build
    you can use '-i' to specify a specifc frontend
    """

    _cmd = [*c.drun, *(c.denv if _is_dev(args) else c.penv), *
            c.vmount_front, "-d", c.front_tag]
    subprocess.run(_cmd)  # start the frontend container

    frontends = _env_as_dict(c.denv[1])["FR_FRONTENDS"]
    assert frontends != ''

    for app in [args.input] if args.input else frontends.split(","):
        _run_in_running(
            _is_dev(args), ["npm", "run", f"build_{app}_{args.btype}"], backend=False)

    kill(args, back=False)  # Kill the frontend container


@register_action(alias=["af"], cont=False)
def attach_front(args):
    """
    Attach to a running frontend container
    currently this will errror if mulitple containers
    """
    _cmd = [*c.drun, *(c.denv if _is_dev(args) else c.penv), *
            c.vmount_front, "-d", c.front_tag]
    subprocess.run(_cmd)
    _run_in_running(_is_dev(args), ["sh"], backend=False)


@register_action(alias=["fb", "bf"], cont=True)
def build_front(args):
    """
    Builds the frontends
    This whole process is dockerized so you don't need any local nodejs installation ( but if wanted a local nodejs installation can be used also )
    1. Build the frontend docker image
    1.5. Copy over env files
    2. Run the container ( keep it running artifically see Dockerfile.front )
    3. Run `npm i`
    4. For all frontends ( check `env.FR_FRONTENDS` ) run `npm i`
    5. For all frontends run webpack build
    6. Kill the frontend container
    """
    env = _env_as_dict(c.denv[1])
    if env["FR_FRONTENDS"] == "":
        print("No frontends present, exiting...")
        return
    frontends = env["FR_FRONTENDS"].split(",")

    if args.input:
        # You can also build the container but only one fronend in it
        print(f"WARN building only {args.input}")
        frontends = [args.input]

    if not _is_dev(args):
        # TODO: in production we might want to do some extra cleanup!
        raise NotImplementedError
    _cmd = [*c.dbuild, *c.front_docker_file, "-t",
            c.front_tag, "./front"]  # <- can just use build context of the fronend dir!
    print(" ".join(_cmd))
    subprocess.run(_cmd)  # 1

    """
    Every frontend has an exchangabol env json file:
    main_frontend.local.env.js <-- for local frontend development ( this is the default env from the repo, but it will not work in the backend use `.dev.env.js` for that )
    main_frontend.dev.env.js <-- env for development in the repo ( if you want to develop font + back at the same time )
    main_frontend.pro.env.js <-- env for poduction or staging
    """
    # Check if such an env exist for current build type

    import shutil

    for front in frontends:
        def _p(t):
            return f"./front/env_apps/{front}.{t}.env.js"
        original_env = f"./front/apps/{front}/src/ENVIRONMENT.js"
        if not os.path.exists(_p("local")) and os.path.exists(original_env):
            # The <app>.local.env.js is basicly a backup of the original env
            print("Backend up original src/ENVIRONMENT.js ")
            shutil.copy(original_env, _p("local"))
        if os.path.exists(_p("dev")):
            # Found replacement env,
            print("Found dev env, overwriting: " + _p("dev"))
            shutil.copy(_p("dev"), original_env)

    _cmd = [*c.drun, *(c.denv if _is_dev(args) else c.penv), *
            c.vmount_front, "-d", c.front_tag]
    subprocess.run(_cmd)  # 2
    _run_in_running(_is_dev(args), ["npm", "i"], backend=False)  # 3
    print(
        f'`npm i` for frontends: {frontends} \nAdd frontends under `FR_FRONTENDS` in env, place them in front/apps/')
    for front in frontends:
        # TODO: there should also be an 'update' option that doesn't install all of this!
        _run_in_running(
            _is_dev(args), ["npm", "i"], work_dir=f"/front/apps/{front}", backend=False)  # 4
    # Frontend builds can only be performed with the webpack configs present
    with open('./front/webpack.template.js', 'r') as f:
        webpack_template = f.read()
    for front in frontends:
        config_path = f'front/webpack.{front}.config.js'
        if not os.path.isfile(config_path):
            # The config doesn't yet exist so we create it from template
            print(
                f"webpack config for '{front}' doesn't yet exist, creating '{config_path}'")
            with open(config_path, 'w') as f:
                f.write(webpack_template.replace("$frontendName", front))
            # Then we also have to add the build command to 'front/package.json'
            # This adds 3 scripts: watch_<front>, build_<front>_dev, build_<front>_prod
            print("Writing new commands to 'front/package.json'")
            with open(f'front/package.json', 'r+') as f:
                package = json.loads(f.read())
                f.seek(0)
                package["scripts"].update({
                    f"watch_{front}": " ".join(_make_webpack_command(env, f'webpack.{front}.config.js', watch=True, debug=True)),
                    f"build_{front}_dev": " ".join(_make_webpack_command(env, f'webpack.{front}.config.js', watch=False, debug=True)),
                    f"build_{front}_prod": " ".join(_make_webpack_command(env, f'webpack.{front}.config.js', watch=False, debug=False)),
                })
                f.write(json.dumps(package, indent=2))
                f.truncate()
        _run_in_running(
            _is_dev(args), ["npm", "run", f"build_{front}_{args.btype}"], backend=False)
    kill(args, back=False)


@register_action(alias=["watch"], cont=False)
def watch_frontend(args):
    """
    Runs the webpack watch command in a new frontend container
    This can be used to watch multiple fontends at the same time!
    & without having node installed or manging npm versions !! :)
    """
    assert args.input, "please input a active frontend: " + \
        str(_env_as_dict(c.denv[1])["FR_FRONTENDS"].split(","))
    assert _is_dev(
        args), "can't watch frontend changes in staging or deloyment sorry"  # ? TODO: why not though?
    # start the frontend container:
    _cmd = [*c.drun, *(c.denv if _is_dev(args) else c.penv), *
            c.vmount_front, "-d", c.front_tag]
    env = _env_as_dict(c.denv[1])
    print("starting container")

    print(" ".join(_cmd))
    subprocess.run(_cmd)

    _cmd = _make_webpack_command(
        _env_as_dict(c.denv[1]), f'webpack.{args.input}.config.js', watch=True, debug=True)
    print(f"generated cmd: {' '.join(_cmd)}")

    def handler(signum, frame):
        print("EXITING\nKilling container...")
        # Also kill redis... cause it starts per default now
        kill(args, front=True, back=False, redis=False)
    signal.signal(signal.SIGINT, handler)
    _run_in_running(_is_dev(args), _cmd, backend=False)


@register_action(alias=["rds", "rd", "redis-server"], cont=True)
def redis(args):
    """
    Runs a local instance of `redis-server` ( required for the chat )
    """
    assert _is_dev(args), "Local redis is only for development"
    # First try to delete to old container if it is present
    _cmd = ['docker', 'rm', c.redis_name[1]]
    subprocess.run(_cmd)

    _cmd = [*c.drun, *c.redis_port, *c.redis_name, "-d", "redis:5"]
    print(' '.join(_cmd))
    subprocess.run(_cmd)


@register_action(alias=["r"])
def run(args):
    """
    Running the docker image, this requires a build image to be present.
    Rebuild the image when ever you cange packages.
    if dev:
        Then container will mount the local `./back` folder,
        and forward port `c.port` (default 8000)
    ** This also automaticly starts the redis instance!
    """
    redis(args)  # <-- start redis!
    return _run(dev=_is_dev(args), background=args.background, args=args)


def _run_tag_env(tag, env, mounts=[], background=False, add_host_route=False, args=None):
    """
    Some variations on `docker run` for interactive / passive container control
    """
    _cmd = [*c.drun, "--env-file", env, *mounts, *(c.host_routes if add_host_route else []),
            * c.port, "-d" if background else "-t", tag]
    print(" ".join(_cmd))
    if background:
        print("BACKGROUND!")
        subprocess.run(_cmd)
    else:
        def handler(signum, frame):
            print("EXITING\nKilling container...")
            # Also kill redis... cause it starts per default now
            kill(args, front=False)
        signal.signal(signal.SIGINT, handler)
        p = subprocess.call(" ".join(_cmd), shell=True, stdin=subprocess.PIPE)


def _run(dev=True, background=False, args=None):
    _run_tag_env(tag=c.dtag if dev else c.ptag, env=(
        c.denv if dev else c.penv)[1], mounts=c.vmount,
        background=background, add_host_route=True, args=args)

    # we print this mainly for port forwarding in codespaces:
    print("Running at localhost:8000 ")


@register_action(alias=["ma", "manage", "manage.py"], parse_own_args=True)
def manage_command(args):
    """ runns a manage.py command inside the container """
    assert args.unknown
    _cmd = args.unknown
    _run_in_running(_is_dev(args), ["python3", "manage.py", *_cmd])


@register_action(alias=["ma_shell_inject", "inject"])
def inject_shell(args):
    """
    Injects a script as text command argument into the python management shell
    NOTE there can be a max lenght of inputable characters in shells
    so in some shells to long script throw an error!
    see _shell_inject/* for exaple scripts

    You can use '!dont_include' as a comment and the line will not be included
    To include a commented line use '!include' somewhere in the comment
    """
    assert args.input, "Please provide a shell script input file"
    import shlex
    script_file_text = ""
    with open(args.input, "r") as f:
        for l in f.readlines():
            if not "!dont_include" in l and not '!include' in l:
                script_file_text += l
            elif '!include' in l:
                script_file_text += l.replace("# !include ", "")
    _cmd = ["python3",
            "manage.py", "shell", "--command", shlex.quote(script_file_text)]
    print(" ".join(_cmd))
    _run_in_running(_is_dev(args), _cmd)


@register_action(name="build_docs", alias=["docs"])
def build_docs(args):
    """
    Can build the spinix documentation inside the docker container
    Note: This assumes you have already build the docker backend container
    """
    assert _is_dev(args), "Can only build docs in development mode"
    _cmd = [*c.dbuild, *c.file_spinix, "-t", c.tag_spinix, "./docs"]
    print(" ".join(_cmd))
    subprocess.run(_cmd)
    _cmd = [*c.drun, *c.denv, *c.vmount_spinix, *c.port, "-d", c.tag_spinix]
    print(" ".join(_cmd))
    subprocess.run(_cmd)
    if os.path.exists("./back/static/docs"):
        print("WARN: found all docs build, overwriting...")
        shutil.rmtree("./back/static/docs")
    _run_in_running_tag(["make", "html"], tag=c.tag_spinix, work_dir="/docs")
    # _run_in_running_tag(["sh"], tag=c.tag_spinix)
    # copy the output files
    # shutil.copytree("./_docs/build/html", "./docs")
    _kill_tag(c.tag_spinix)
    shutil.copytree("./_docs/build/html", "./back/static/docs")


@register_action()
def reset_migrations(args):
    """
    Deltes all migration files appart from the __init__.py
    You can call ./run.py rest_migrations -i git to register deleted files with git
    """
    import glob  # This one required glob to be installed
    select_paths = [*glob.glob(f"{os.getcwd()}/back/*/migrations/*"),
                    *glob.glob(f"{os.getcwd()}/back/*/*/migrations/*")]
    # otherwise cause of symlink cookie_consent would be considered twice:
    select_paths = [p for p in select_paths if not "_cookie_consent_repo" in p]
    migration_files = [p for p in select_paths if not (
        '__init__.py' in p or '__pycache__' in p)]
    print(f"Deleting migrations files: {migration_files}")
    if args.input and args.input == "git":
        for p in migration_files:
            _cmd = ["git", "rm", "-f", p]
            print(f"del: {' '.join(_cmd)}")
            subprocess.run(_cmd)
    else:
        for p in migration_files:
            print(f"del: {p}")
            os.remove(p)


@contextlib.contextmanager
def _conditional_wrap(cond, before, after):
    """
    allowes for if with statements
    if contidion = True it will execute before before and after after
    """
    if cond:
        before()
    yield None
    if cond:
        after()


if USE_BASH_AUTOMCOMPLETION:
    print("using auto completion")
    argcomplete.autocomplete(_parser())

if __name__ == "__main__":
    """
    Entrypoint for `run.py`
    Using the script requires *only* docker and python!
    e.g:
    `./run.py ?`:
        Show basic doc/ help message
    `./run.py`:
        Default; Build, then run development container
    `./run.py build run redis`:
        Also start redis server for local dev
    `./run.py shell`:
        Login to `c.shell` on a *running* container
    """
    set_parser(_parser)
    parse_actions_run()
