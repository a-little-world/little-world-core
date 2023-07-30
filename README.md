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
./run.py
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

For any frontend in `./front/apps/<frontend-name>/`
With config `./front/webpack/<frontend-name>.config.js`
If the file `./front/env_apps/<frontend-name>.<build-type>.env.js` is present, it's used to replace `./front/apps/<frontend-name>/src/ENVIRONMENT.js`

### Kill containers

```
./run.py k
```
      
### Making Feature Deployments via Pull Request

1. Makes changes on a feature branch in the frontend repo `frontend-feature-branch`
2. Clone the backend repo, checkout a new branch `git checkout -b staging-<some-feature-name>`
3. Initalize submodules `git submodule --init --recursive`
4. Go into the frontend sub repo you changed - in case of user_form - `cd /front/apps/user_form`
5. Pull your feature branch `git pull && git switch staging-<some-feature-name>`
6. Add the updated sub repo commit `git add /front/apps/user_form && git commit -m "feature implementation XXXX"`
7. Push branch: ``
8. Go to pull request on github.com

> Note the `staging-` prefix for the branch name, if that is provided a temporary env will be created on pull request

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