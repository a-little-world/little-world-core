# Frontend simulation tests (isolated setup)

This folder is intentionally isolated from backend test setup:

- Separate test location under `dev/`
- Separate virtual environment in `dev/e2e_simulations/.venv`
- Separate Python dependencies in `dev/e2e_simulations/requirements.txt`

## What this starter suite tests

- Public routes render the frontend shell:
  - `/login`
  - `/sign-up`
  - `/forgot-password`
  - `/reset-password`
  - `/email-preferences`
- `/login` includes the non-hidden cookie banner script
- `/app/` redirects unauthenticated users to `/login?next=/app/`

## Run

From repo root:

```bash
bash dev/e2e_simulations/run.sh
```

Custom base URL:

```bash
E2E_BASE_URL="http://localhost:8000" bash dev/e2e_simulations/run.sh
```

Custom Python binary for the venv:

```bash
E2E_PYTHON_BIN="python3" bash dev/e2e_simulations/run.sh
```

Pass pytest args:

```bash
bash dev/e2e_simulations/run.sh -k login -vv
```

Run with visible browser windows:

```bash
bash dev/e2e_simulations/run.sh --headed
```

Run slowed-down simulation steps (default 250ms/action):

```bash
bash dev/e2e_simulations/run.sh --slow
```

Set a custom delay in milliseconds:

```bash
bash dev/e2e_simulations/run.sh --slow=700
```

Combine both (recommended for visual debugging):

```bash
bash dev/e2e_simulations/run.sh --headed --slow=700 -k login -vv
```

## Host requirements

- Chromium dependencies required by Playwright (script installs the browser itself)
- `libstdc++.so.6` available on host (on Debian/Ubuntu usually from `libstdc++6`)

## Add simulation tests

Create files under `dev/e2e_simulations/tests/` and use Playwright `page` fixture:

1. `page.goto(...)`
2. `page.fill(...)`
3. `page.click(...)`
4. Assert URL and visible elements

If you need authenticated flows, add a login helper (UI login or API-based setup) in `conftest.py`.
