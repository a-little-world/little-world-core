## Backend Development

For backend development, you need a local Python installation (version > 3.7) and a local Docker installation. All backend and frontend build processes can be performed with `run.py`. It generally uses default Python libraries, but some command actions require additional packages.

> Note that we are currently moving to a more transparent build process using `Makefiles`.

### Installation

The installation steps have to be performed once in the beginning of the setup. Later, only specific components need to be updated. For example, when developing in the backend, you would only rebuild the backend container if you wanted to add another package to `requirements.txt`.

```bash
git clone ...
cd ...

# Performs setup and builds all Docker containers for front + back
./run.py
# First execution can take a while
# Alternatively, you can manually perform the build steps:
./run.py setup
./run.py build
./run.py build_front
./run.py trans
./run.py static
./run.py run
```

### Development

After completing the installation, simply run `./run.py r` to start the container. The development container opens at `localhost:8000` and mounts the local code repository. It can listen to any changes in static files and backend files and will hot reload.

There are some dummy environment files provided in `env -> dev_env`. If these are changed, the container has to be restarted.

### Test Users

Currently, the test database is empty by default. You can generate some users by:

```bash
./run.py inject -i _shell_inject/create_20_testusers.py
```

You can extend that script for different variations of user accounts. We might provide some example datasets in the future.

The default admin credentials are configured in `DJ_MANAGEMENT_USER_MAIL` & `DJ_MANAGEMENT_PW`. The development defaults are `admin@user.com` and `Test123!`.

> Note that the admin user will be created automatically when the first user is added/registered, so you can only log in at `/admin/` once you have created the test users!

### More info on build tools

All build steps are simple actions in `./run.py`. See the module description or help pages for that tool for more information on the build steps.
