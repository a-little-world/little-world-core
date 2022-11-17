#!/usr/bin/env python3
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
    denv = ["--env-file", "./env"]
    penv = ["--env-file", "./penv"]
    shell = "/bin/bash"
    redis_port = ["-p", "6379:6379"]

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


subprocess_capture_out = {
    "capture_output": True,
    "text": True
}


def _parser():
    """
    Commandline args:
    most notably 'actions'
        the default ( -> `./run.py` ) is configured for development to run the following steps
        1. Build docker image ( required for all the following steps)
        2. static extraction
        3. mirations for the db
        4. running the container interactively ( close with ctl-C )
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--btype', default="dev", help="prod, dev, any")
    parser.add_argument('-bg', '--background',
                        action="store_true", help="Run the docker container in background (`./run.py kill` to stop)")
    parser.add_argument(
        '-o', '--output', help="Ouput file or path required by some actions")
    parser.add_argument(
        '-i', '--input', help="Input file (or data) required by some actions")

    # default actions required by tim_cli_utils (TODO: they should be moved there)
    parser.add_argument('actions', metavar='A', type=str, default=["_setup",
                        "build", "static", "migrate", "run"], nargs='*', help='action')
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
    for tag in [c.ptag, c.dtag, c.front_tag, c.staging_tag]:
        ps = _running_instances(tag)
        all_running += ps if isinstance(ps, list) else [ps]
    print(all_running)
    return all_running


def _running_instances(tag=TAG):
    """ Get a list of running instance for docker 'tag' """
    _cmd = ["docker", "ps", "--format",
            r"""{"ID":"{{ .ID }}", "Image": "{{ .Image }}", "Names":"{{ .Names }}"}"""]
    out = str(subprocess.run(_cmd, **subprocess_capture_out).stdout)
    ps = [eval(x) for x in out.split("\n") if x.strip()]
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
    assert len(ps) == 1, "where to attach? please specify -i " + \
        "\"{'ID':'...'}\""
    subprocess.run(["docker", "container", "attach", ps[0]["ID"]
                   if len(ps) == 1 else eval(args.input)["ID"]])


@register_action(cont=True, alias=["k"])
def kill(args, front=True, back=True):
    """ Kills all the running container instances (back & front)"""
    for tag in [c.front_tag if front else None,
                c.dtag if back else None,
                c.ptag if not _is_dev(args) else None]:
        if tag:
            _kill_tag(tag)


def _kill_tag(tag):
    ps = _running_instances(tag)
    _cmd = ["docker", "kill"]
    for p in ps:
        _c = _cmd + [p["ID"]]
        print(' '.join(_c))
        subprocess.run(_c)


def _run_in_running(dev, commands, backend=True, capture_out=False, work_dir=None):
    """
    Runns command in a running container.
    Per default this looks for a backend container.
    It will look for a frontend container with backend=False
    """
    return _run_in_running_tag(
        commands=commands,
        tag=(c.dtag if dev else c.ptag) if backend else FRONT_TAG,
        capture_out=capture_out,
        work_dir=work_dir)


def _run_in_running_tag(commands, tag, capture_out=False, work_dir=None, extra_docker_cmd=[]):
    """
    Runns command in a running container, with a specific tag
    """
    ps = _running_instances(tag)
    assert len(ps) > 0, "no running instances found"
    _cmd = ["docker", "exec",
            *(["-w", work_dir] if work_dir else []), *extra_docker_cmd, "-it", ps[0]["ID"], *commands]
    if not capture_out:
        subprocess.run(" ".join(_cmd), shell=True)
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


def _build_file_tag(file, tag):
    _cmd = [*c.dbuild, "-f", file, "-t", tag, "."]
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
    if 'DOCS' in aws_env and aws_env['DOCS'].lower() in ('true', '1', 't'):
        # Also build the documentation and move it to /static
        build_docs(args)
        # Copy the build files to
        shutil.copytree("./docs", "./back/static/docs")
    # Build the frontends
    build_front(args)
    # Collect the statics ( also contains the files for open api specifications )
    build(args)  # Required build of the 'dev' image
    extract_static(args)
    # Build Dockerfile.stage
    _build_file_tag(c.file_staging[1], c.staging_tag)
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
    _build_file_tag(c.file[1], c.dtag if _is_dev(args) else c.ptag)


@register_action(alias=["static", "collectstatic"], cont=True)
def extract_static(args, running=False):
    with _conditional_wrap(not running,  # If the containers isn't running we will have to start it
                           before=lambda: _run(_is_dev(args), background=True),
                           after=lambda: kill(args, front=False)):
        # '--noinput' why ask for overwrite permission we are in container anyways
        _run_in_running(_is_dev(args), ["python3", "manage.py",
                        "collectstatic", "--noinput"])


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

    if not _is_dev(args):
        # TODO: in production we might want to do some extra cleanup!
        raise NotImplementedError
    _cmd = [*c.dbuild, *c.front_docker_file, "-t",
            c.front_tag, "."]
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
    assert args.input, "please input a active frontend: " + \
        str(_env_as_dict(c.denv[1])["FR_FRONTENDS"].split(","))
    assert _is_dev(
        args), "can't watch frontend changes in staging or deloyment sorry"
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
    _run_in_running(_is_dev(args), _cmd, backend=False)


@register_action(alias=["rds", "rd", "redis-server"])
def redis(args):
    """
    Runs a local instance of `redis-server` ( required for the chat )
    """
    assert _is_dev(args), "Local redis is only for development"
    _cmd = [*c.drun, *c.redis_port, "-d", "redis:5"]
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
    """
    return _run(dev=_is_dev(args), background=args.background)


def _run_tag_env(tag, env, mounts=[], background=False):
    """
    Some variations on `docker run` for interactive / passive container control
    """
    _cmd = [*c.drun, "--env-file", env, *mounts,
            *c.port, "-d" if background else "-t", tag]
    print(" ".join(_cmd))
    if background:
        subprocess.run(_cmd)
    else:
        def handler(signum, frame):
            print("EXITING\nKilling container...")
            kill(None, front=False)
        signal.signal(signal.SIGINT, handler)
        p = subprocess.call(" ".join(_cmd), shell=True, stdin=subprocess.PIPE)


def _run(dev=True, background=False):
    _cmd = [*c.drun, *(c.denv if dev else c.penv), *c.vmount,
            *c.port, "-d" if background else "-t", c.dtag if dev else c.ptag]
    _run_tag_env(tag=c.dtag if dev else c.ptag, env=(
        c.denv if dev else c.penv)[1], mounts=c.vmount, background=background)

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
    """ Injects a script into the python management shell """
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
    _cmd = [*c.dbuild, *c.file_spinix, "-t", c.tag_spinix, "."]
    print(" ".join(_cmd))
    subprocess.run(_cmd)
    _cmd = [*c.drun, *c.denv, *c.vmount_spinix, *c.port, "-d", c.tag_spinix]
    print(" ".join(_cmd))
    subprocess.run(_cmd)
    #_run_in_running_tag(["make", "html"], tag=c.tag_spinix, work_dir="/docs")
    _run_in_running_tag(["sh"], tag=c.tag_spinix)
    # copy the output files
    shutil.copytree("./_docs/build/html", "./docs")
    _kill_tag(c.tag_spinix)


@register_action()
def reset_migrations(args):
    import glob  # This one required glob to be installed
    select_paths = [*glob.glob(f"{os.getcwd()}/back/*/migrations/*"),
                    *glob.glob(f"{os.getcwd()}/back/*/*/migrations/*")]
    # otherwise cause of symlink cookie_consent would be considered twice:
    select_paths = [p for p in select_paths if not "_cookie_consent_repo" in p]
    migration_files = [p for p in select_paths if not (
        '__init__.py' in p or '__pycache__' in p)]
    print(f"Deleting migrations files: {migration_files}")
    for p in migration_files:
        print(f"del: {p}")
        os.remove(p)


def _action_by_alias(alias):
    for act in ACTIONS:
        if alias in [*ACTIONS[act]["alias"], act]:
            return act, ACTIONS[act]
    else:
        raise Exception(f"Action or alias '{alias}' not found")


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
