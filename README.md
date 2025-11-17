# Little World Backend

The backend consists of a django application that is containerized using docker.
Builds are manged using docker compose.
This repo also builds all frontends using webpack and serves them via django views.

## Servers

1. All feature pull request starting with `staging-*` are auto-deployed. Without credentials!
2. All commits merged into [`main`](https://github.com/a-little-world/little-world-backend/tree/main) are deployed to [`from-v2.little-world.com`](https://from-v2.little-world.com) ( temorarily deploying to `stage.little-world.com` will be used for a security check )
3. All commits merged into [`prod`](https://github.com/a-little-world/little-world-backend/tree/prod) are deployed to any production config.
   E.g.: [`little-world.com`](https://little-world.com), [`shareami.little-world.com`](https://shareami.little-world.com)

> Production and staging deployments NEED TO BE CONFIRMED by an admin!

## Development Build

You can do all backend development using docker compose and a few simple command.
You can also develop all the frontends from within the backend repo, with full code + hot reloading.

### Perpare Development Repo

1. create a venv `python3 -m venv ./venv` then source it `source /venv/bin/activate`
2. install all backend packages `pip install -r back/requirements.txt`
3. install development packages `pip install -r back/requirements.dev.txt`
4. activate the ruff pre-commit hook `pre-commit install` ( else your formatting check will likely fail )

### Full Hot-Reload Back & All Frontends

setup:

```bash
git clone <backend> && cd little-world-backend
git submodule update --init --recursive
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml build
for frontend in main_frontend admin_panel_frontend cookie_banner_frontend; do touch ./front/$frontend.webpack-stats.json ; done
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml up
```

To also use the `patenmatch` frontend run:

```bash
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml build patenmatch
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml up patenmatch

# OR for all-in-one + patenmatch

COMPOSE_PROFILES=all-pt docker compose -f docker-compose.dev.yaml up
```

To reset the networking use `docker network prune` and to recreate add `--force-recreate` to the up command.

Once you have run `docker compose up` with the `=all` flag at least once you can also run only specific frontends with auto-update:

e.g.:

```
COMPOSE_PROFILES=main_frontend docker compose -f docker-compose.dev.yaml up
```

or run some tests:

```bash
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml exec backend sh -c "python3 manage.py test management.tests.test_register"
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml exec backend sh -c "python3 manage.py test management.tests"
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml exec backend sh -c "python manage.py test emails --parallel"
```

That's it! Any code changed in `/front/apps/*/src/*` or in `/back/*` will cause a hot-reload for the specific frontend, or backend.

Be sure to checkout the frontend commit or branch you want to work on!

> If you wan't only one frontend to auto-update just use `COMPOSE_PROFILE=<frontend-name>` for any frontend `main_frontend`, `admin_panel_frontend`, `cookie_banner_frontend`.
> Or if you only work in the backend use `COMPOSE_PROFILE=backend`

### Default Test Users

All these should be auto-created on first backend startup ( to reset them just delete the local db `rm ./back/db.sqlite3` and restart the backend ).

- 'Matching User': `tim.timschupp+420@gmail.com:Test123!` Can visit `/matching/`
- 'Admin User': `admin@user.com:Admin123!` Can visit `/admin/` ( must login at `/admin/login` )
- 'Test -Users': `herrduenschnlate+<id>@gmail.com:Test123!` with any `<id>` from `1` to `20` Can visit only `/app/`

### Usefull Urls

- Swagger UI view: `localhost:8000/api/schema/swagger-ui/`
- DB Overview ( requires admin login ): `localhost:8000/db/`

### Frontend Configuration

- Frontends are subrepos in `./front/apps/<frontend-name>`
- `<frontend-name>` should be listed in `FR_FRONTENDS`
- configure the environment in `docker-compose.yaml:services.all.evironment`
  or `./envs/dev.env` for local development
- specify `BUILD_TYPE=<build-type>` to change frontend environments
  `<build-type>=dev` for local developent and `<build-type>=pro` for staging
- on build; `./front/env_apps/<frontend-name>.<build-type>.env.js` replaces `./front/apps/<frontend-name>/src/environment.ts`

### Django debugging

Debugging for the django backend is enabled by default during development. To connect to the backend:

- Start the backend container using the docker-compose.dev.yaml
- In VSCode navigate to the debug tab and run the Debug (Django) configuration
- If everything is set up correctly the VSCode debugger should now be connected to the django backend inside docker
- Now you can set you breakpoints inside VSCode

### WSL Notes

git Line config needs to be changed:

```pswh
git config --global core.autocrlf false
```

## Production Build

Use and build the production contains locally.

#### TL;DR full docker build

Want to test a feature quickly locally:

```
git clone <your-feature-branch> && cd little-world-backend
git submodule update --init --recursive
docker compose build
```

> Quciker build meant for testing, check below for development setup

### Run Tests ( as you should before making a PR )

Use this to verify locally if your features breaks anything, rather than waiting for the CI!

```
docker compose build
docker run -d --name redis-test -p 6379:6379 redis
docker compose run all python manage.py test
docker rm -f redis-test
```