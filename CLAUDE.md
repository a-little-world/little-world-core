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
pnpm run start          # webpack watch (dev)
pnpm run build          # production build
pnpm exec tsc --noEmit  # type-check without emitting
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

### Survey campaigns

In-app surveys are configuration, not code. `SurveyCampaign` declares audience, active window,
trigger, eligible-after condition, `repeat_scope`, `available_via_link` and `questions`;
`SurveyResponse` holds one row per *offer*, unique on `(campaign, user, context_key)`.

- `context_key` is `""` for once-per-user campaigns and `live_session:<uuid>` for once-per-call
  ones — one field lets both kinds share one table and one uniqueness rule. It is never `NULL`.
- There are two delivery channels, and both are plain HTTP GETs. There is deliberately no
  WebSocket delivery path: the old post-call survey used one and failed silently for a year.
  - **Popup:** `GET /api/surveys/pending`, polled by the main app.
  - **Link:** `GET /api/surveys/<slug>` for campaigns with `available_via_link`, rendered at
    `/app/surveys/<slug>` with the same `Survey` card. A campaign can be a popup, a link, or
    both. With trigger `none` it is link-only (`clean()` requires `available_via_link`).
- Both channels share the one offer row. A link visit creates it with
  `delivery_channel=link` and sets `opened_at`; pending delivery skips link rows, so a link
  visit never turns into a popup later. Link visits never touch `shown_at` / `shown_count`, so
  they do not start the cooldown or count toward `max_shows`. Only a submitted answer closes
  the link: a popup that was dismissed, or expired after `max_shows`, can still be answered at
  the URL. Switching a campaign to trigger `none` also stops popups for offers already open.
- Rows are created when the survey is offered, never bulk-inserted at launch, so eligibility
  stays dynamic and `shown_count` staying flat is a visible delivery failure.
- A user is shown at most one card per `SHOW_COOLDOWN` (12h), across *every* campaign, not
  per offer. The client refetches the pending endpoint as soon as a survey closes, so a
  per-offer rule would hand over the next campaign's card immediately. A user inside the
  quiet period is offered nothing and creates nothing; offers an event trigger already wrote
  stay open and are delivered once the window passes, so deferring a survey never loses it.
  `shown_at` is only written when the client confirms it rendered the card, so an offer that
  never displayed does not start the window.
- Answered questions are immutable (id, type, referenced choice options). A rating
  question's `scale` cannot change once that question has been answered — growing or shrinking
  would change what existing scores mean. Enforced in `SurveyCampaign.save()`, not in admin.
  Rating is a question type, not a campaign setting: a campaign can have several ratings, or
  none. Each rating carries its own scale (2–10). `SurveyCampaign.scale` is only a fallback for
  older rating questions saved without a scale. There is no rating column on `SurveyResponse`;
  answers live in `answers` JSON and means are computed per rating question.
- Question types are rating (stars), text, choice (one option, `RadioGroup` on the main app)
  and multiselect (checkboxes). Choice and multiselect share `{value, label}` options; only
  the widget and the answer shape differ. Multiselect answers are stored as a unique JSON
  array in **option order**, not click order — `[events, chat]` and `[chat, events]` are the
  same answer. Empty list is unanswered.
- Audience is everyone, a company already on `state.company`, or one of the shared
 banner/event/survey filters (`AudienceFilters`). Picked from a single dropdown in the admin panel.
- Trigger is when the popup is offered: `on_session`, after a non-qualifying call (under 10
  minutes), after a qualifying call (10 minutes or longer), or `none` (link only). Eligible-after is a
  named journey condition: immediately, onboarded (`state.is_onboarded`), first qualifying
  call (standard calls only, not random, 10 minutes or longer, both active), match created, halfway to match success
  (half the live `management.match_success` token threshold), or match success (the shared
  `management.match_success` definition). Conditions take effect as soon as they are true.
  Optional `eligible_after_since` is a lower bound on when that condition counts — e.g.
  onboarded on or after 31 Aug 2025. Match conditions qualify if *any* of the user's matches
  satisfy them; support matches and the signup admin chat do not count. Once-per-user
  campaigns still offer the survey only once. `starts_at` / `ends_at` are the campaign
  calendar: after `ends_at` nobody is offered the survey.
- Copy lives on the campaign row as `{de, en}` (campaign title/description/submit plus
  per-question labels), not in frontend locale files. German is required to activate; English
  falls back to it. Completeness is validated in `SurveyCampaign.save()` only on activation, so
  drafts can be saved half-finished. The pending endpoint resolves copy for the user's
  `display_language` before it leaves the backend.
- On the main app, the card validates on submit (react-hook-form): required questions show a
  field error rather than a disabled button. Closing the popup submits only if at least one
  question is answered and every required one is; otherwise it dismisses. A failed submit also
  falls back to dismissing. Clicking the backdrop does not close it.
- Responses are read in the admin panel's Responses view: one sheet of answers per row, and,
  with a campaign filter, answered/offered plus a mean per rating question computed from
  `answers` JSON.
- Campaigns are created and edited in the admin panel (`Communications → Surveys`), not via
  management commands. Logic lives in `management/surveys.py`; a new survey is a new row.

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
