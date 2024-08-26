"""
.. include:: ./docs_nav.md

# Little World Documentation

This is the full documentation for Little World.

The documentation is still under development. For questions or additions, email `tim@timschupp.de`.

All our documentation is behind a simple login mask. The links contained here are configured to automatically log you in (this will only work with cookies & JavaScript enabled).

### The `little-world-backend` Repository

Little World components can be developed independently, e.g., developing frontends shouldn't require building the backend locally (for more info, see the dev-guides).

#### Submodules

- Cookie Consent Management System: [`back/cookie_consent`](https://github.com/a-little-world/little-world-cookie-consent)
- Chat: [`back/chat`](https://github.com/a-little-world/little-world-private-chat.git)
- Main Frontend: [`front/apps/main_frontend`](https://github.com/a-little-world/little-world-frontend.git)
- Cookie Banner: [`front/apps/cookie_banner_frontend`](https://github.com/a-little-world/little-world-cookie-banner.git)

Most tasks will not require access to all these; we should always strive to keep necessary access to a minimum.

##### Adding Submodules

All Django apps that we maintain or use a fork of shall be linked as a submodule into `./back/`.
All frontends should be linked in `./front/apps/`.

`git submodule add <repo-url> <path> --name <some-name>`

> Frontends should also be added to `FR_FRONTENDS` in `./env`.

### API Documentation

- [Interactive Swagger Documentation](https://s1.littleworld-test.com/api/user/login?token=devUserAutoLoginTokenXYZ&u=devuser@mail.com&l=email&n=/api/schema/swagger-ui/)
- [Static Redoc Documentation](https://s1.littleworld-test.com/api/user/login?token=devUserAutoLoginTokenXYZ&u=devuser@mail.com&l=email&n=/api/schema/redoc/)

We always use session-based authentication, so you need to pass the session cookie with every request.
Also, we require a CSRF token for every POST request!

Generally, we accept requests with JSON-encoded bodies and return JSON streams.

### Backend Documentation

- [Backend Config Module and Development Guide](/back/)
- [Backend User Management Module](/management/)
- [Email Module (also contains previews for all emails)](/emails/)
- [Tracking Module](/tracking/)

### Frontend Documentation

- [Frontend Development Guide](/front/)
- [Design Sheet](/design/)
- [Figma (might need to request access)](/figma/)

### Contributing

Generally, you make pull requests to the main branch, which will run our CI.
Our test coverage is not very high, but this does some basic tests and also checks if all strings have been translated, etc.

Pull requests to the main branch can be deployed to our staging server upon request to `tim@timschupp.de`.
Once tested, it's best to add a few integration tests if it's a backend PR. We don't currently do integration testing for our frontends ( we should though ;) ).
"""
