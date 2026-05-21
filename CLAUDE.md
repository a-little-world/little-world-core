# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Development Commands

All services run via Docker Compose. The default profile starts backend + admin panel frontend:

```bash
docker compose up                          # backend + admin_panel_frontend + redis
docker compose --profile all up            # all services including all frontends
docker compose --profile main_frontend up  # backend + main frontend only
```

**Backend (Django):**
```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations management --name <description>
docker compose exec backend python manage.py create_test_support_task <email>
docker compose exec backend python manage.py shell
```

**Frontend (admin panel):**
```bash
cd front/apps/admin_panel_frontend
npm run start          # webpack watch (dev)
npm run build          # production build
npx tsc --noEmit       # type-check without emitting
```

**Linting:**
```bash
ruff check back/        # Python linting (configured in ruff.toml at repo root)
ruff format back/       # Python formatting
```

The `ruff.toml` excludes migrations, `_cookie_consent_repo`, and `venv`. Line length is 120.

---

## Repository Structure

```
back/           Django project root
  back/         Django settings, urls, wsgi/asgi
  management/   Main application (see below)
  chat/         WebSocket chat via Django Channels
  video/        LiveKit video calls
  tracking/     Analytics / conversion event logging
  emails/       Transactional email templates
  patenmatch/   Separate matching sub-app

front/
  apps/
    admin_panel_frontend/   React + TypeScript management panel
    main_frontend/          Public-facing React app
    cookie_banner_frontend/ Cookie consent banner
```

---

## Backend Architecture

### Django setup
- Custom user model: `management.User` (`AUTH_USER_MODEL`)
- `DEFAULT_AUTO_FIELD = BigAutoField`
- ASGI with Django Channels for WebSocket chat
- Celery with Redis broker; results stored in Django DB (`django-db` backend)
- Two authentication paths: session auth (admin panel) and `NativeOnlyJWTAuthentication` (mobile app — requires `{"client": "native"}` JWT claim)

### `management` app layout

```
management/
  models/           One file per model; all exported via __init__.py
  api/              One file per API surface; each exposes api_urls = [...]
  actions/          Support task action handlers (see below)
  signals.py        Django post_save signals for automatic task creation
  urls.py           Assembles all api_urls into urlpatterns
  permissions.py    ManagementPermission enum (StrEnum)
  authentication.py NativeOnlyJWTAuthentication
  tasks.py          Celery tasks (startup tasks, background jobs)
  controller.py     High-level user lifecycle operations
```

### Support task system

Tasks are the unit of work for the support team. Key invariants:
- Every `SupportTask` has exactly one `SupportTaskAction` (1:1, `OneToOneField`)
- Tasks are always created via `SupportTask.create_of_type(task_type, ...)` — never via `objects.create()` directly
- Task type (e.g. `"support_reply"`) is the primary concept; it bundles an action type + title/description lambdas
- `SupportTaskAction.resolve(new_status, reviewed_by)` completes the action **and** auto-completes the task

**Action registry** (`management/actions/registry.py`):
- `@register(action_type, static_schema=..., param_schema=...)` — registers a handler with typed dataclass schemas
- `register_task_type(task_type, action_type=..., task_title=..., task_description=...)` — registers a task type
- `autodiscover()` (called in `ManagementConfig.ready()`) imports all modules in `management/actions/` to trigger registrations

**Action modules** in `management/actions/`:
- `support_reply.py` — created automatically when a `HelpMessage` is saved (via signal)
- `change_profile_value.py` — country of residence, user type changes
- `profile_review.py` — suspicious profile, incomplete profile
- `remove_match.py` — match removal requests

**History** (`management/models/object_history.py`): Generic `ObjectHistory` model using Django `ContentType` framework. `SupportTask` and `SupportTaskAction` both have `GenericRelation(ObjectHistory)`. History entries are written automatically in the model `save()` overrides (CREATE on first save, UPDATE on field diffs). Tracked fields: `SupportTask` → title, description, status, priority, assigned_to_id; `SupportTaskAction` → status, parameters.

### API pattern

All API endpoints are function-based views using `@api_view`, `@authentication_classes`, `@permission_classes`. Each api module exports `api_urls = [path(...), ...]` which is imported and flattened in `management/urls.py`.

---

## Frontend Architecture (Admin Panel)

**Stack:** React 19 + TypeScript + Webpack + Tailwind CSS + styled-components + SWR

**Design system:** `@a-little-world/little-world-design-system` (source at `../little-world-design-system/packages/web/`). Always prefer DS components before writing new ones. See `front/apps/admin_panel_frontend/styles.md` for the full style guide.

The full style guide lives in `front/apps/admin_panel_frontend/CLAUDE.md`. Key rules:
- All CSS in `styled-components` — no inline `style={{}}` props
- Use `theme.*` tokens for colors, spacing, radius
- Table pages: `createColumnHelper` + `<DataTable>` + `useSearchParams`
- Toolbar: `<FiltersToolbar>` with `<Dropdown>` children
- Filter modals: per-page `*Filters.tsx` following `Filters.tsx` Modal+Card pattern
- Status/type pills → `<Tag appearance={TagAppearance.outline} color={...}>`
- User avatars → `<UserImage>`

**Routing:**
- Routes defined in `src/routes.ts`, registered in `src/App.tsx`, added to nav in `src/components/blocks/Menu.tsx`
- Base path: `/matching/`

**API calls:** `src/api/helpers.ts` exports `apiFetch<T>(endpoint, options)` — handles CSRF, JSON, error formatting. Individual modules in `src/api/` wrap `apiFetch` for each domain.

**State management:** URL search params (`useSearchParams`) for filter/sort/page state. SWR for server state. Zustand-style global state in `src/store.tsx` for selected users and user list data.

---

## Database

Development uses SQLite (`/back/db.sqlite3`). Production uses PostgreSQL (profile `postgres` in compose). Migrations live in `back/management/migrations/` — always generate with a descriptive `--name`.

After deleting the local database and restarting, migrations run automatically on startup.
