# Little World Backend

The backend consists of a django application that is containerized using docker.
Builds are manged using docker-compose. 
This repo also builds all frontends using webpack and serves them via django views.

> It's always recomended to use `DOCKER_BUILDKIT=1` it is the future default for docker anyways and speeds up builds significantly

## Servers 

1. All feature pull request starting with `staging-*` are auto-deployed. Without credentials!
2. All commits merged into `main` are deployed to [`stage.little-world.com`](https://stage.little-world.com)
3. All commits merged into `prod` are deployed to any production contig.
E.g.: [`little-world.com`](https://little-world.com), [`shareami.little-world.com`](https://shareami.little-world.com),
[`form-v2.little-world.com`](https://form-v2.little-world.com)

> Production and staging deployments NEED TO BE CONFIRMED by an admin!

## TL;DR full docker build

Want to test a feature quickly locally:

```
git clone <your-feature-branch> && cd little-world-backend
git submodule update --init --recursive
DOCKER_BUILDKIT=1 docker-compose build
```

> Quciker build meant for testing, check below for development setup

### Run Tests ( as you should before making a PR )

Use this to verify locally if your features breaks anything, rather than waiting for the CI!

```
DOCKER_BUILDKIT=1 docker-compose up -d
docker-compose all exec python3 manage.py test
docker-compose down
```

## Backend ( + Frontend in Backend ) Development

You can do all backend development using docker-compose and a few simple command.
You can also develop all the frontends from within the backend repo, with full code + hot reloading.

### Full Hot-Reload Back & All Frontends

setup:

```
git clone <backend> && cd little-world-backend
git submodule update --init --recursive
COMPOSE_PROFILES=all DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml build
for frontend in main_frontend user_form user_form_frontend admin_panel_frontend cookie_banner_frontend; do touch ./front/$frontend.webpack-stats.json ; done
COMPOSE_PROFILES=all DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml up
```

Once you have run `docker-compose up` with the `=all` flag at least once you can also run only specific frontends with auto-update:

e.g.:
```
COMPOSE_PROFILES=main_frontend DOCKER_BUILDKIT=1 docker-compose -f docker-compose.dev.yaml up
```

That's it! Any code changed in `/front/apps/*/src/*` or in `/back/*` will cause a hot-reload for the specific frontend, or backend.

Be sure to checkout the frontend commit or branch you want to work on!

> If you wan't only one frontend to auto-update just use `COMPOSE_PROFILE=<frontend-name>` for any frontend `main_frontend`, `user_form` (v2), `user_form_frontend`, `admin_panel_frontend`, `cookie_banner_frontend`.
Or if you only work in the backend use `COMPOSE_PROFILE=backend`


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

```
git clone github.com/a-little-world/little-world-backend.git && cd little-world-backend
git submodule --init --recursive
git checkout -b staging-<your-feature-branch>
cd ./front/apps/user_form/
git pull && git switch <your-feature-branch> # or 'main'
cd ../ && git add ./user_form && git commit -m "update user form" # update commit refence
git push # Now go to github.com/a-little-world/little-world-backend/tree/<your-feature-branch> & create a pull request
```

Check the messages in the pull request, in a few minutes you can test your features live.

## Infrastructure

The development chat, as its also used by our Ephemeral environments.

### Local Microk8s

You can also run the whole infrastucture locally

```
microk8s enable ingress registry helm
touch .env
echo "APP_IMAGE_URL=\"localhost:32000/backend:registry\"" >> .env
echo "REDIS_URL=\"http://host.docker.internal:6379\"" >> .env
DOCKER_BUILDKIT=1 docker-compose build
DOCKER_BUILDKIT=1 docker-compose push
microk8s helm install release-1 ./helm/
```

Wait for containers to deploy

```
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
