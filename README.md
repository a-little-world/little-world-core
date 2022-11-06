# django clean slate by tbscode

![Django Tests + Container Build](https://github.com/tbscode/django-clean-slate/actions/workflows/tests.yaml/badge.svg)
![Build Docs](https://github.com/tbscode/django-clean-slate/actions/workflows/docs.yaml/badge.svg)
![Staging Deployment](https://github.com/tbscode/django-clean-slate/actions/workflows/stage.yaml/badge.svg)

This is a clean slate fullstack web setup.

system requirements: `python > 3.8`, `docker`

> This refects ( in part ) the stack used on little-world.com

## The stack

The whole stack is fully dockerized.

Backend:

- django ( 4.1.2 )
  - General backend routing and authentication
- channels ( 4.0.0 )
  - async asgi application interface and websocket handlers
- celery ( 5.2.7 )
  - background ad reoccuring task management

Frontend:

- django-webpack ( serving bundles )
- react app(s) ( bundled with webpack )

> As alternative to serving static js bundles this stack might be updated to use django-nextjs

## Deployment

The 'staging' version is currently deployed at: https://django-clean-slate-staging.herokuapp.com/

The **production** application is suppsed to be deployed with Kubernetes `k8s.io` ( configurations are **not included** in this repo ).
For production I recommend a pooled postgressql database, a redis memory store (for websocket support), a s3 storage bucked for serving static files and a load balanced k8 node pool. This configuration allowes full horizontal - on demand - scaling.

This repo offers a **staging** deployment! For staging we can easily use [`white-noise`](http://whitenoise.evans.io/en/stable/) to serve static files, a simple in-container redis instance and a simple in-container sqllite database. This can be auto deployed on a free-tier Heroku instance - or similar - using the `Dockerfile.stage` in combination with a github [workflow](https://github.com/tbscode/django-clean-slate/actions/workflows/stage.yaml).

## Documentation

Are automaticly generated using `sphinx` and published to [`gh-pages`](https://tbscode.github.io/django-clean-slate).
Docs can be generated localy using `./run.py docs` or automaticly using a github [workflow](https://github.com/tbscode/django-clean-slate/actions/workflows/docs.yaml).

e.g.: see full documentation of [`./run.py`](https://tbscode.github.io/django-clean-slate/apidoc/extra_mods.run.html#module-extra_mods.run).

### API documentation

Using [`drf-spectacular`](https://github.com/tfranzel/drf-spectacular) to generate open api schemas from DRF.
Open API shemas for swagger and redoc are avaiable at:

- [`/api/schema/swagger-ui/`](https://django-clean-slate-staging.herokuapp.com/api/schema/swagger-ui/)
- [`/api/schema/redoc/`](https://django-clean-slate-staging.herokuapp.com/api/schema/redoc/)

## Tools

`run.py` manages full docker and frontend builds.

For info run `./run.py ?` or check the script.

## Known issues

- [ ] Permissions for inconter created files, outputed at volume mount are docker group

> There sadly is still not right way to manage volume permissions in docker: https://github.com/moby/moby/issues/7198,
> Though we can fix this by adding the system user group inside of the container and using that for creating all the files
