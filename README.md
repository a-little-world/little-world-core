# Little World Backend

## TL;DR full docker build

Want to test a feature quickly locally:

```
git clone <your-feature-branch>
git submodule --init --recursive
DOCKER_BUILDKIT=1 docker-compose up --build
```

## Backend Development

Auto setup, full hot reload for code in `./back/*`

```
./run.py # Use `./run.py r` on subsequent runs to skip builds
```

### Frontend + Backend Development

```
./run.py
./run.py watch -i <frontend-name> # or one-time update ./run.py uf -i <frontend-name>
```

#### Build Frontend

```
./run.py bf # or ./run.py bf -i <frontend-name>
```

> Only if packages.json updated, `./run.py` also automaticly updates frontends

#### Frontend Configuration

- Frontends are subrepos in `./front/apps/<frontend-name>`
- `<frontend-name>` should be listed in `FR_FRONTENDS`
- configure the environment in `docker-compose.yaml:services.all.evironment`
or `./env` for local development
- specify `BUILD_TYPE=<build-type>` to change frontend environments
`<build-type>=dev` for local developent and `<build-type>=pro` for staging
- `./front/env_apps/<frontend-name>.<build-type>.env.js` replaces `./front/apps/<frontend-name>/src/ENVIRONMENT.js`

### Kill containers

```
./run.py k
```
      
### Making Feature Deployments via Pull Request
      
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

Check for contains to deploy

```
microk8s kubectl get pods
... once ready visit localhost / https://localhost:80
```