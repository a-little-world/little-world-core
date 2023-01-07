### Gettings started on backend development

For backend development you need a local python installation (> 3.7) and a local docker installation.
All backend and frontend build processes can be performed with `run.py`. It generaly used default python libaries but some command actions require additional packages.

### installation

The instalation steps have to performed once in the beginning of setup.
Later only specifc components need to be updated.
E.g.: when developing in the backend you'd only rebuild the backend container if you wanted to add another package to `requirements.txt`.

```bash
git clone ...
cd ...

# performs setup and builds all docker containers front + back
./run.py
# first execution can take a while
# alternatively you can manually perform the build steps:
./run.py setup
./run.py build
./run.py build_front
./run.py trans
./run.py static
./run.py run
```

### development

When you completed the installtion only run `./run.py r` to start the container.
The delopment container opens at `localhost:8000` and mounts the local code reposetory.
So it can listen to any changes in static files and backend files and will hot reload.

There are some dummy environment files provided in `env -> dev_env`.
If these are changed the container has to be restarted.

### test users

Currently the test db is empty dy default. You can generate some user by:

```bash
./run.py inject -i _shell_inject/create_20_testusers.py
```

You can extend that script for different variation on the user accounts.
We might provide some example datasets in the future.

The default admin credentials are configured in `DJ_MANAGEMENT_USER_MAIL` & `Admin123!`.

### more info on build tools

All build steps are a simple action in `./run.py` see to module description or helpages for that tool for more inforation on the build steps.
