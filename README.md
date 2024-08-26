# Little World Backend (v 0.92)

The backend consists of a django application that is containerized using docker.
Builds are manged using docker compose.
This repo also builds all frontends using webpack and serves them via django views.

> It's always recomended to use `DOCKER_BUILDKIT=1` it is the future default for docker anyways and speeds up builds significantly

## Servers

1. All feature pull request starting with `staging-*` are auto-deployed. Without credentials!
2. All commits merged into [`main`](https://github.com/a-little-world/little-world-backend/tree/main) are deployed to [`from-v2.little-world.com`](https://from-v2.little-world.com) ( temorarily deploying to `from-v2.little-world.com` as `stage.little-world.com` will be used for a security check )
3. All commits merged into [`prod`](https://github.com/a-little-world/little-world-backend/tree/prod) are deployed to any production config.
   E.g.: [`little-world.com`](https://little-world.com), [`shareami.little-world.com`](https://shareami.little-world.com)

( 4. Commits merged into [`form-v2`](https://github.com/a-little-world/little-world-backend/tree/form-v2) are deployed to [`form-v2.little-world.com`](https://form-v2.little-world.com). )

> Production and staging deployments NEED TO BE CONFIRMED by an admin!

## TL;DR full docker build

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

## Backend ( + Frontend in Backend ) Development

You can do all backend development using docker compose and a few simple command.
You can also develop all the frontends from within the backend repo, with full code + hot reloading.

### Full Hot-Reload Back & All Frontends

setup:

```bash
git clone <backend> && cd little-world-backend
git submodule update --init --recursive
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml build
for frontend in main_frontend admin_panel_frontend cookie_banner_frontend; do touch ./front/$frontend.webpack-stats.json ; done
COMPOSE_PROFILES=all docker compose -f docker-compose.dev.yaml up
```

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

### Documentation

```bash
cp README.md ./back/docs_template/README.md
docker compose -f docker-compose.docs.yaml build
docker compose -f docker-compose.docs.yaml up
```

Add this command block to the compose to quickly rebuild the docs on every up command

```bash
    command: sh -c 'python3 generate_docs.py && sh ./back/entries/docs_entry.sh'
```

View the local development docs at `localhost:8000/static/` ( other routes that `/static/` do not work in the docs container )

#### Frontend Configuration

- Frontends are subrepos in `./front/apps/<frontend-name>`
- `<frontend-name>` should be listed in `FR_FRONTENDS`
- configure the environment in `docker-compose.yaml:services.all.evironment`
  or `./envs/dev.env` for local development
- specify `BUILD_TYPE=<build-type>` to change frontend environments
  `<build-type>=dev` for local developent and `<build-type>=pro` for staging
- on build; `./front/env_apps/<frontend-name>.<build-type>.env.js` replaces `./front/apps/<frontend-name>/src/ENVIRONMENT.js`

### Ephemeral Environments: Making Feature Deployments via Pull Request

To deploy a staging version of your changes all you need to do is:

1. create a feature branch starting with `staging-*`
2. make some changes
3. create pull request to main

e.g.: updating the user-form frontend

```bash
git clone github.com/a-little-world/little-world-backend.git && cd little-world-backend
git submodule --init --recursive
git checkout -b staging-<your-feature-branch>
cd ./front/apps/main_frontend/
git pull && git switch <your-feature-branch> # or 'main'
cd ../ && git add ./main_frontend && git commit -m "update user form" # update commit refence
git push # Now go to github.com/a-little-world/little-world-backend/tree/<your-feature-branch> & create a pull request
```

Check the messages in the pull request, in a few minutes you can test your features live.

### WIP Capacitor Android ( & IOS )

Build android `.apk's` for local testing this process is still experiemental and will be simplified in the future.

```bash
# 0. Extract current `apiTranslations` and `apiOptions`
COMPOSE_PROFILES=main_frontend docker compose -f docker-compose.dev.yaml up -d
curl -X 'GET' \
  'http://localhost:8000/api/options_translations/' \
  -o front/apps/main_frontend/src/options_translations.json
# 1. Replace the env
cp front/env_apps/main_frontend.capacitor.env.js front/apps/main_frontend/src/ENVIRONMENT.js
# 2. create a frontend static build
COMPOSE_PROFILES=main_frontend docker compose -f docker-compose.dev.yaml exec frontend__main_frontend /bin/bash -c "
  cd /front/apps/main_frontend/ && npm i
  cd /front/apps/main_frontend/ && ./node_modules/.bin/webpack --env PUBLIC_PATH= --env DEV_TOOL=none --env DEBUG=0 --mode production --config webpack.capacitor.config.js
  cd /front/apps/main_frontend/ && ./node_modules/.bin/cap sync
"
COMPOSE_PROFILES=main_frontend docker compose -f docker-compose.dev.yaml down
# 3. Then build the android app in a container ( SEE ALTERNATE )
docker compose -f docker-compose.capacitor-dev.yaml up
docker compose -f docker-compose.capacitor-dev.yaml down
# 4. reset env
cd front/apps/main_frontend && git stash -- src/ENVIRONMENT.js
```

Alternatively for hot-reload emulator development after step 2 run

```bash
cd front/apps/main_frontend/
./node_modules/.bin/webpack --env PUBLIC_PATH= --env DEV_TOOL=eval-cheap-module-source-map --env DEBUG=1 --mode development --config webpack.capacitor.config.js
# for low footprint, non debug build use:
# ./node_modules/.bin/webpack --env PUBLIC_PATH= --env DEV_TOOL=none --env DEBUG=0 --mode production --config webpack.capacitor.config.js
./node_modules/.bin/cap sync

# Start the emulator
./node_modules/.bin/cap run android

# Start the backend:
COMPOSE_PROFILES=backend docker compose -f docker-compose.dev.yaml up
```

## Infrastructure

The development chat, as its also used by our Ephemeral environments.

### Local Microk8s

You can also run the whole infrastucture locally

```bash
microk8s enable ingress registry helm
touch .env
echo "APP_IMAGE_URL=\"localhost:32000/backend:registry\"" >> .env
echo "REDIS_URL=\"http://host.docker.internal:6379\"" >> .env
docker compose build
docker compose push
microk8s helm install release-1 ./helm/
```

Wait for containers to deploy

```bash
watch microk8s kubectl get pods
```

once ready visit `http://localhost`

## Attaching to live DB

Sometimes it can be convenient to use the django ORM to make queries to the DB from your local machine. Thats what `docker-compose.prod-attach.yaml` is for.
You will need to place the credentials into `.env.prod-attach` then run:

```bash
export $(grep -v '^#' .env.prod-attach | xargs) && docker compose -f docker-compose.prod-attach.yaml build
export $(grep -v '^#' .env.prod-attach | xargs) && docker compose -f docker-compose.prod-attach.yaml up
```

e.g.: Run a management command, just edit a file in `./back/management/management/commands/<command-name>.py`.
Then run it via:

```bash
export $(grep -v '^#' .env.prod-attach | xargs) && docker compose -f docker-compose.prod-attach.yaml exec app ./manage.py <command-name>
```

### Setting up pylint locally

1. create a venv `python3 -m venv ./venv` then source it `source /venv/bin/activate`
2. install all backend packages `pip install -r back/requirements.txt`
3. setup vscode linting config

```json
  "python.pythonPath": "/home/tim-schupp/Data/local/development/little-world/little-world-backend/pythonenv/bin",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.linting.pylintUseMinimalCheckers": false,
  "python.linting.pylintArgs": [
    "--load-plugins",
    "pylint_django",
    "--django-settings-module=example.settings"
  ]
```

## Installing or updating our livekit components

Use: [`./_scripts/update_livekit_components.sh`](./_scripts/update_livekit_components.sh)

This will:

- if not present clone [our livekit fork](https://github.com/a-little-world/components-js) into `./components-js`
- if present clear some build files
- install dependencies `pnpm install`
- build the react package `pnpm build`
- extract and increase the patch version number of the react components package `0.0.XXX`
- bundle the react package `pnpm bundle` ( in `./components-js/packages/react` )
- copy the bundle to `./front/apps/main_frontend/prebuild/` and update the `package.json` there with the new version