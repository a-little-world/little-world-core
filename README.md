## Little World Backend V2

The awesome clean an refurbished version of `little-world-dev-backend`

> This fullstack setup is based on [`tbscode/django-clean-slate`](https://github.com/tbscode/django-clean-slate) please check that repo for additional information on the stack

### Gettings started

Only requirement for the backend are `docker` & `python > 3.8`

**All** the build are handled by `./run.py`. To get started:

```shell
chmod u+x run.py
./run.py <TAB> # only if you have autocompletion, see below
./run.py ?
```

Simply running `./run.py` will install all required packages, clone all required submodules, build the required images ( here `Dockerfile.front` builds all frontends and `Dockerfile.dev` builds the backend ) and run the images.

For more check the doc-page of [`./run.py`](TODO).

### TAB autocompletion

If you do `pip3 install argcomplete` and then run `eval "$(register-python-argcomplete run.py)"`
you will have auto completion for actions and options!

> Tipp: If you only want to see available actions but not their alias use `./run.py -a <TAB>`

### Documentation

API's and docs are currently served at `staging.littleworld-test.com`. ( Status: )

- Repo code documentation [`static/docs`](TODO)
- Backend API documentation [`api/shema/swagger-ui`](TODO)

### Backend Development

Per default for development the local `./back` folder is mounted inside the backend docker container, and codechanges in here **will hot-reload**.
Keep in mind that hot-reloading doesn't work for django static files templates and settings!
Static file and template change require `./run.py build`, with some exceptions see 'Frontend Development' below.

### Frontend Development

Frontend are can be developed fron inside the backend but this is not recommended!
We recommend to start a backend instance in the background (`./run.py -bg`, `./run.py kill` to kill).
Then run you frontend instance from a seperate directory ( you cloned from `a-little-world` git before ), just like you'd do normally `npm start`.

Configure (see `frotend/example` ), then start [`schroedingers-nginx.sh`](https://github.com/tbscode/schroedingers-nginx), this will route all api and media routes ( e.g.: `/api/`, `/api2/`, `/media/`, `/admin/`) **and** you npm dev server ( expected at `localhost:3000` ) to the url `localhost:3333`.

Be sure to be on `localhost:3333` from here you'll be able to authenticate your session with test users and make api calls just as if you where running from within the backend.

### Test users and test data

We **don't** ship a populated sqlite db with this development version!
We do only offer a basic database fixture `instertName.json`, this is loaded per default on the inital `run.py`.
Alternatively you can run `./run.py setup` to load the fixture without starting the server.

#### Default Users

Test users (`user:pw`):

- `benjamin.tim@gmx.de:Test123!` ( basic user )
- `herrduenschnlate@gmail.com:Test123!` ( basic user )
- `admin@little-world.com:Admin123!` ( test admin user )

#### Security and admin users

You wont be able to login as admin at `/api/user/login` this is blocked!
Andmin users can only login at `admin/login/?opensesame`, note `?opensesame` will be different in production!

In poduction only admin users may render the paths: `/db`, `/api/schema/*`, `/admin/*`

### Handling Translations

For helping with translations and sharing them we have [`little-world-translations`](https://github.com/a-little-world/little-world-translations.git)

But how do translations work in the background?

Philosophy here is to keep the individual translations where they belong; frontend texts in frontends, backend and api texts in backend.

> It is _Never_ encouraged to overwite API translation in the frontend!
> Though we do offer to request tags instead of trasnlations by adding `?use_tags=true`

#### Making tranlations

`./run.py make_messages -i <app>` searches all python files of that app for `_(...)` translations and create django.po files from that.

> This will warn you when a original tag has changed, but if you overwite `/<app>/locale/aka/djang.po` youre responsible of handling the frontend tag update!

`./run.py trans` will compile all the `django.po` translation files to `django.mo` files.

> Note: our policy is to commit `django.po` files but not `django.mo` files, they are build automaticly on first startup!

> Also note we don't yet have any CI check of the sanity of our translations (if every tag used by the frontend does exist in the backend)! TODO @tbscode

### Adding Submodules

All django apps that we maintain or use a fork of shall be linked as submodule into `./back/`.
All frontend should be linked in `./front/apps/`.

`git submodule add <repo-url> <path> --name <some-name>`

> Frontends should also be added to `FR_FRONTENDS` in `./env`

#### Existing submodules

- Cookie Consent management system [`back/cookie_consent`](https://github.com/a-little-world/little-world-cookie-consent)
- Chat [`back/chat`](https://github.com/a-little-world/little-world-private-chat.git)

- Main Frontend [`front/apps/main_frontend`](https://github.com/a-little-world/little-world-frontend.git)
- User Form [`front/apps/user_form_frontend`](https://github.com/a-little-world/little-world-user-form.git)
- Cookie Banner [`front/apps/cookie_banner_frontend`](https://github.com/a-little-world/little-world-cookie-banner.git)

### Staging

Want to see you change in a deployed status with limited key / security access? No problem!
First ask @tbscode for development deployment credentials, then run:

```shell
./run.py staging -i "{'...'}" TODO
```
