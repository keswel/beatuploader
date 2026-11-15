# Beatuploader: agent guide

Beatuploader is a free, donation-supported **Windows desktop app** that
uploads a producer's beats to BeatStars and YouTube in one go. Everything
runs on the producer's PC (a Tauri shell plus a local FastAPI sidecar serving
a React UI). **Nothing is stored on our servers.** `beatuploader.app` is only
the marketing site and download.

```
desktop/   Tauri v2 shell (Rust)       → desktop/README.md for build + release
frontend/  React 19 + Vite + Tailwind  → two builds: website and desktop app UI
backend/   FastAPI + async SQLAlchemy  → desktop sidecar (LOCAL_MODE) or legacy hosted API
```

**How everything works is in [`ARCHITECTURE.md`](./ARCHITECTURE.md).**

## Workflow

1. **Before a large change, read `ARCHITECTURE.md`.** At minimum read the
   sections you'll touch. A large change is a new feature, a new platform,
   anything touching auth, security, storage, the upload pipeline, the
   desktop shell or release, or a change across more than one of
   backend/frontend/desktop. For a small, local fix, reading the code is
   enough.
2. **Make the change.** Follow the conventions below and the patterns in the
   surrounding code.
3. **Review your work before calling it done:**
   - Re-read your full diff (`git diff`) as a reviewer would. Look for bugs,
     edge cases, leftover debug code, unrelated changes, and stale comments.
   - Run the checks that apply and read their output:
     - backend → `cd backend && python -m pytest tests/`;
     - frontend → `cd frontend && npm run build && npm run build:desktop`
       (both builds type-check);
     - shell → `cd desktop/src-tauri && cargo check`.
   - When behaviour changed, exercise it for real where you can (run the
     sidecar, hit the endpoint, load the page). If you couldn't verify
     something, say so plainly instead of implying it works.
   - Check that you didn't break the other build target. Website-only code
     must not leak into the desktop app, and the reverse.
4. **Update `ARCHITECTURE.md` in the same change** whenever it would
   otherwise be wrong. That includes new or changed:
   - endpoints, connectors, models or migrations;
   - data flow;
   - security behaviour;
   - build, release or infrastructure;
   - status in the platform table or the known-gaps list.

   Describe the current state only; git holds the history. If you notice
   something there that's already stale, fix it. Update `AGENTS.md` when you
   establish a new convention or rule.

## General practices

- Keep changes focused. Don't refactor, rename or reformat unrelated code in
  the same change.
- Match the existing style and patterns of the file you're in, and reuse
  existing helpers before writing new ones.
- Prefer the simplest thing that works. Don't add an abstraction, dependency
  or config option for a hypothetical future need.
- Comments explain *why*, not *what*. Delete comments your change made
  untrue.
- Add or update tests for backend logic you change, especially connectors,
  auth and security. Connector tests use an httpx `MockTransport`; never hit
  live platform APIs in tests.
- Never commit secrets, `.env` files, HAR captures (`*.har` carry live
  tokens) or `storage/` (diagnostics hold logged-in DOM).
- Pin new dependencies to a specific, established version.
- **Git:** never credit an AI as author or co-author. That means no
  `Co-Authored-By: Claude…` trailers and no "Generated with…" lines in
  commits, PRs or release notes. When squash-merging, set the commit body
  explicitly. Work on a branch and open a PR; don't push to `main`.

## Codebase conventions

### Product rules
- **Desktop first.** New features target the desktop app. Don't build on
  hosted-only paths (accounts, email, Google sign-in). That code is legacy.
- **Privacy is a promise.** The app must never send user data to us: no
  analytics, telemetry or crash reporting in the desktop build. The website
  may use Vercel Web Analytics only. If what we collect changes, update
  `frontend/src/pages/legal/privacy.tsx` (and its `updated` date) in the
  same change.
- **Never store platform passwords.** Store the session or tokens only,
  Fernet-encrypted.

### Backend (`backend/`)
- Async everywhere (SQLAlchemy 2.0 async). Don't add sync DB sessions.
- Routers live in `app/api/` and are mounted in `app/api/router.py`. Decide
  explicitly whether a new router is mounted in local mode, hosted mode or
  both.
- Use `DbSession` and `CurrentUser` from `deps.py`. In local mode
  `CurrentUser` is the implicit local user.
- Request and response bodies are Pydantic schemas in `app/schemas/`. Never
  return ORM models; use a `_serialize` helper for derived fields (see
  `api/uploads.py`). Every user-controlled string field gets a `max_length`.
- **JSON columns:** always reassign (`job.targets = dict(targets)`), never
  mutate in place.
- **Errors:** never send exception text to the client. Log it with
  `log.exception(...)` and return a generic message.
- Every schema change gets an Alembic migration in `backend/alembic/versions/`.
  Migrations run on boot (always on desktop; behind `RUN_MIGRATIONS_ON_BOOT`
  when hosted). Desktop uses SQLite and hosted uses Postgres, so they must
  work on both.
- Rate-limit new unauthenticated or expensive endpoints with
  `limit_dependency(...)` from `services/rate_limit.py`.
- Keep `WindowsProactorEventLoopPolicy` at the top of `app/main.py`.
  Playwright is sync, wrapped in `asyncio.to_thread`; don't switch to async
  Playwright.
- Hash passwords with bcrypt directly (`security.py`), not passlib.

### Platform connectors (`backend/app/services/platforms/`)
- A new platform is one file implementing `PlatformConnector`, plus a
  `registry.py` entry. Override `is_configured()` if it needs operator
  credentials, so the UI shows "Coming soon" instead of a broken button.
- Connectors that refresh or rotate sessions must hand back `session_data`,
  even on failure (`exc.session_data`). BeatStars refresh tokens rotate, and
  losing one forces a reconnect.
- BeatStars: keep the "rules learned from the first live run" in
  `ARCHITECTURE.md` (wait for asset processing, genre required, server
  clock, never send Basic). The default is the HTTP connector; the
  Playwright path is only a fallback. **BeatStars caps SMS codes per day, so
  test connect sparingly.**
- Report progress through `progress_cb`, throttled the way `jobs.py`
  already does it.

### Frontend (`frontend/`)
- `lib/api.ts` is the only module that talks to the backend. Keep
  `lib/types.ts` in sync with the Pydantic schemas by hand.
- Use TanStack Query for server data, and `qc.invalidateQueries(...)` after
  mutations. Every data view needs loading, empty and error states (see
  `pages/library.tsx`).
- Gate target-specific code on `IS_DESKTOP` from `lib/target.ts`. Website
  routes and desktop routes are separate trees in `App.tsx`.
- Use `useAuth()` for the user; don't pass the user through props. Use
  `<AuthedImage>` for images behind auth.
- Import animation from `motion/react` (not framer-motion). Keep the
  sidebar's `layoutId="sidebar-pill"`.
- **App look:** dark and monochrome (zinc-950), colour only for state, iOS
  spring easing, `.lift` / `.glass`. Don't add colour for decoration.
- **Website look:** the light cut-paper collage, styled in
  `pages/landing.css` under `.landing`, with chrome from
  `components/site-chrome.tsx`. Don't mix it with the app's dark styles.
- A new top-level app page needs a nav entry in both `components/sidebar.tsx`
  and `components/mobile-nav.tsx`.
- Desktop dashboard links go to `/dashboard`, never `/`.

### Desktop shell & release (`desktop/`)
- The served UI gets **no Tauri IPC**; only the bundled splash does. Don't
  expose commands to the loopback page.
- The sidecar must exit when its stdin closes. Don't remove that.
- Bump the version in all three of `tauri.conf.json`, `Cargo.toml` and
  `desktop/package.json`, then push a `v<version>` tag.
  **Never run the release workflow without a version bump.** It publishes
  into the existing release and replaces the installer the website links to.
- Pushing a tag publishes an update to every install. Only do it when asked.

### Dev environment
- The backend dev port is **8001** (`start-backend.ps1`, `BACKEND_BASE_URL`,
  `frontend/.env.local`, Google redirect URIs). Change them all together or
  not at all.
- The primary dev machine is Windows (PowerShell scripts, `.venv\Scripts`).
  Keep paths and scripts Windows-compatible.
