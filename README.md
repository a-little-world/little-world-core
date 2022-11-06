### Little World Backend V2

The awesome clean an refurbished version of `little-world-dev-backend`

> This fullstack setup is based on [`tbscode/django-clean-slate`](https://github.com/tbscode/django-clean-slate) please check that repo for additional information on the stack

### Gettings started

**All** the build are handled by `./run.py`.
Check `./run.py ?` for help text on possible commands ( don't forget to `chmod u+x run.py` ).

> Only requirement for the backend are `docker` & `python > 3.8`

Simply running `./run.py` will install all required packages, clone all required submodules, build the required images ( here `Dockerfile.front ( all frontneds )` and `Dockerfile.dev ( the backend )` ) and run the images.

For documentation check the doc-page of [`./run.py`](TODO).

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

```python
./run.py staging -i "{'...'}" TODO
```
