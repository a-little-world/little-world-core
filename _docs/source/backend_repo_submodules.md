## Little World submodules

These are all bigger modular/ independant software components.

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
