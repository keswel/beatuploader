# Architecture

How Beatuploader works. Read this before making a large change, and update it
in the same change whenever what's described here stops being true (see
`AGENTS.md`). This file describes the current state of the system. Git holds
the history, so don't add changelog entries here.

## Contents

1. [Product](#product)
2. [Repo layout](#repo-layout)
3. [Desktop app (the product)](#desktop-app-the-product)
4. [Backend](#backend)
5. [Platform connectors](#platform-connectors)
6. [Upload pipeline](#upload-pipeline)
7. [Frontend](#frontend)
8. [Data model](#data-model)
9. [Security model](#security-model)
10. [Hosting & infrastructure](#hosting--infrastructure)
11. [Hosted mode (legacy)](#hosted-mode-legacy)
12. [Known gaps](#known-gaps)

---

## Product

A beat upload tool for independent producers. You connect BeatStars and
YouTube once, then push each beat to every platform in one go. It's **free and
donation-supported**.

The product is a **Windows desktop app**. Everything runs on the producer's
machine, and **nothing is stored on our servers**: no credentials, no files,
no accounts. The website (`beatuploader.app`) only markets the app and
distributes the installer. An older hosted multi-user version of the backend
still runs on Render, but nothing links to it (see
[Hosted mode](#hosted-mode-legacy)).

Planned: a background tray app that notices a finished FL Studio export,
prompts for metadata, and uploads it.

## Repo layout

```
beatuploader/
├── desktop/        Tauri v2 shell (Rust): window, tray, sidecar lifecycle, auto-updater
│   ├── src-tauri/src/main.rs     the whole shell
│   ├── splash/                   bundled splash page (the only page with Tauri IPC)
│   └── README.md                 build / release runbook
├── frontend/       Vite + React 19 + TS + Tailwind v4 + motion + TanStack Query
│                     npm run build          → dist/          the website
│                     npm run build:desktop  → dist-desktop/  the app UI
├── backend/        FastAPI + async SQLAlchemy 2.0 + Pydantic v2 + Alembic
│   ├── app/desktop.py            desktop sidecar entrypoint (LOCAL_MODE=true)
│   ├── app/main.py               FastAPI app, middleware, SPA serving
│   ├── app/api/                  routers (mounted under /api by api/router.py)
│   ├── app/services/             jobs, storage, rate limiting, email, platforms/
│   ├── app/models/  app/schemas/ ORM models / Pydantic schemas
│   ├── alembic/                  migrations (run on boot)
│   └── desktop.spec              PyInstaller onedir build of the sidecar
├── .github/workflows/desktop-release.yml   builds + publishes releases on a v* tag
├── render.yaml  DEPLOY.md  neon.ts         hosted-mode infra
└── start*.ps1                              Windows dev launchers
```

## Desktop app (the product)

```
beatuploader.exe (Tauri shell)            window, tray, single-instance, updater
 └─ backend/beatuploader-backend.exe      PyInstaller build of backend/app/desktop.py
     └─ serves frontend/dist-desktop      same origin: http://127.0.0.1:<port>/
```

**Startup** (`desktop/src-tauri/src/main.rs`):
1. Pick a free loopback port and generate a random per-launch session secret.
2. Spawn the sidecar with `BEATUPLOADER_PORT`, `BEATUPLOADER_SESSION`, and the
   YouTube OAuth client. The client ID and secret are compiled into the shell
   from `BEATUPLOADER_YOUTUBE_CLIENT_ID/SECRET` via `option_env!`.
3. Show the bundled splash until `GET /health` answers, then navigate the
   window to `http://127.0.0.1:<port>/dashboard`.
4. Closing the window hides it to the tray. Tray → Quit exits.

In debug builds the shell runs `python -m app.desktop` from the repo venv
(`.venv/Scripts`) with a visible console.

**Sidecar** (`backend/app/desktop.py`) sets `LOCAL_MODE=true`, points
`FRONTEND_DIST_DIR` at the bundled UI, logs to a rotating file, and **exits
when its stdin closes**. The shell holds that pipe, so if the shell dies the
backend dies too. It is never orphaned and never keeps file locks that would
break the updater.

**Local mode** (`config._apply_local_mode`):
- Data lives in `%APPDATA%\Beatuploader\` (`~/.beatuploader` elsewhere):
  `beatuploader.db` (SQLite), `storage/`, `logs/backend.log`. Alembic migrates
  on every boot.
- The Fernet key that encrypts platform tokens lives in **Windows Credential
  Manager** (`keyring`, service `Beatuploader`, `app/local_secrets.py`). It
  falls back to a file only if the vault is unavailable.
- The JWT secret is random per process and only signs OAuth `state`.
- **No accounts.** `deps.get_current_user` returns one implicit local user,
  auto-created. Only `GET/PATCH /api/auth/me` are mounted (`api/router.py`).
  Register, login, password, Google sign-in and waitlist routes don't exist.
- CORS is off: the UI is served from the backend's own origin.
- The request gate is `main.LocalSessionMiddleware` (see
  [Security model](#security-model)).

**YouTube OAuth on desktop.** Google blocks OAuth inside embedded webviews, so
`POST /platforms/youtube/connect` calls `webbrowser.open()` and returns
`external: true`. The callback renders a "you can close this tab" page, and
the Platforms page polls until `connected_at` changes. This needs a Google
client of type **Desktop app**, which accepts any `http://127.0.0.1:<port>`
redirect.

**Bundle.** Playwright is excluded from the PyInstaller build. Its imports in
`beatstars.py` and `_browser.py` are optional, so the desktop app only uses
the BeatStars HTTP connector. The installer is NSIS, per-user (no admin), and
about 26 MiB.

**Auto-update and releases.** `tauri-plugin-updater` checks
`https://github.com/keswel/beatuploader/releases/latest/download/latest.json`
on launch and from tray → "Check for updates". Pushing a `v*` tag runs
`.github/workflows/desktop-release.yml`, which:
- builds the frontend, the sidecar and the shell;
- signs the update;
- publishes the release and `latest.json`;
- also uploads the installer as the fixed-name `Beatuploader-setup.exe` that
  the website links to.

The version must match in `desktop/src-tauri/tauri.conf.json`,
`desktop/src-tauri/Cargo.toml` and `desktop/package.json`. The workflow names
the release from `tauri.conf.json`, so running it without bumping the version
overwrites the current release's assets.

The signing private key is `~/.tauri/beatuploader-updater.key` (no password),
stored as the repo secret `TAURI_SIGNING_PRIVATE_KEY`. **If it's lost, every
install is stuck on its current version.** The repo must stay public so
release downloads work anonymously. Full runbook: `desktop/README.md`.

## Backend

- FastAPI, async everywhere (SQLAlchemy 2.0 async sessions). Routers live in
  `app/api/` and are mounted under `/api` by `app/api/router.py`. Which
  routers are mounted depends on `local_mode`.
- `GET /health` is liveness and doesn't touch the DB. `GET /health/ready` also
  checks the DB.
- In local mode `main.py` also serves the SPA from `FRONTEND_DIST_DIR`. It
  injects the session token into `index.html` and falls back to `index.html`
  for client routes.
- `main.py` sets `WindowsProactorEventLoopPolicy` at the top of the module,
  before any other import. Uvicorn's default selector loop on Windows can't
  start subprocesses, which Playwright needs. Headless code uses **sync
  Playwright inside `asyncio.to_thread`** (`services/platforms/_browser.py`).
- **Migrations:** `init_db()` runs `alembic upgrade head` on boot, gated by
  `RUN_MIGRATIONS_ON_BOOT`. `python -m app.migrate` is the standalone
  equivalent for a pre-deploy step.
- **Config:** `app/config.py` (pydantic-settings). There's no `backend/.env`
  in dev; it runs on defaults. `_validate_secrets` warns about weak secrets
  when `DEBUG=true` and refuses to boot when `DEBUG=false`.
- **Rate limiting** (`services/rate_limit.py`) is an in-memory,
  per-IP sliding window attached per route through `limit_dependency(...)`.
  It only works with a single process.

### Dev

```powershell
./start.ps1                     # both servers in separate windows; restart/kill prompt
# or manually:
cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload --port 8001
cd frontend; npm run dev        # http://localhost:5173
cd backend; python -m pytest tests/
```

The backend dev port is **8001**, hardcoded in `start-backend.ps1`. Windows
leaves zombie listeners on 8000 after a hard kill. `BACKEND_BASE_URL` is
`http://localhost:8001` so OAuth redirects match, and `frontend/.env.local`
has `VITE_API_BASE=http://127.0.0.1:8001/api`. To change the port, update all
of these together, plus the Google Console redirect URIs.

First-time setup: `python -m venv .venv && .venv\Scripts\python -m pip install -e ".[dev]"`.
Add `playwright install chromium` only if you need the legacy BeatStars path.

## Platform connectors

`backend/app/services/platforms/`. Every upload target implements
`PlatformConnector` (`base.py`):

```
start_authorize(user_id, redirect_uri) → OAuthRedirect     # OAuth only
complete_authorize(code, state, redirect_uri) → dict       # OAuth only
disconnect(connection)
upload(connection, file_path, meta, progress_cb=None) → UploadHandle
poll(connection, handle) → UploadProgress
is_configured() → bool    # has the operator-provided credentials it needs
```

`AuthMethod` is `oauth`, `headless` (username/password) or `api_key`
(unused). `registry.py` maps `PlatformProvider` to a connector. Adding a
platform means writing one file and adding one registry entry.

`is_configured()` defaults to `True`. OAuth connectors return whether their
client ID is set. `GET /platforms` exposes it as `PlatformOut.configured`.
The frontend shows an unconfigured platform as **"Coming soon"** (disabled),
and only an explicit `false` does that, so a backend that lags behind the
frontend never hides a working platform.

| Platform | Status | Notes |
|---|---|---|
| YouTube | Working | Google Data API v3. Uploads are created **private**. Uses a user-supplied video if present, else the audio (YouTube renders it as a black-frame video). The refreshed access token is written back to the DB. Progress per chunk. |
| BeatStars | Working, verified live from the desktop app | HTTP connector by default. Playwright fallback behind `BEATSTARS_USE_HTTP=false`. |
| SoundCloud | Built, not live | OAuth2 + PKCE, multipart `/tracks` upload. Blocked on getting app credentials, which needs an Artist Pro account. Auth-header scheme and field names aren't yet checked against the live API. |
| Spotify / Audiomack / Bandcamp | Enum entries only | No connector files. |

### BeatStars over HTTP (`_beatstars_http.py`, the default)

Reverse-engineered from the studio.beatstars.com web client. It's plain
`httpx` with no browser: standard OAuth2, GraphQL, and S3 presigned POST.

**Auth:**
- Login is `POST core.prod.beatstars.net/auth/oauth/token` with
  `grant_type=password`. An `identifierAvailable` GraphQL check runs first so a
  missing account gets a clear error.
- The access token lasts about 30 days and the refresh token about a year.
  **The refresh token rotates on every refresh.**
- The password is **never stored**. When the refresh token dies, the connector
  raises `BeatStarsSessionExpired` (a `PlatformSessionExpired`) and the job
  runner flags the connection so the user reconnects.
- Because of rotation, a failed upload still returns its refreshed session in
  `exc.session_data`, and `jobs.py` persists it. Drop that and the user is
  forced to reconnect.
- The stored session is JSON:
  `{access_token, refresh_token, expires_at, member_id, account_label}`.
- The OAuth client ID and secret are baked into BeatStars' own frontend, so
  they're effectively public.

**SMS 2FA** (`_complete_mfa`):
- It triggers reliably from datacenter IPs and rarely from home IPs.
- The plain password grant sends the SMS automatically and returns
  `MFA_VERIFICATION_ACTION`.
- Verifying uses the `/auth/graphql` mutation
  `verifyMfa({verifyMfaRequest:{identifier, pin}})`. `identifier` is the
  resolved BeatStars **username** (`profileDetails.username`), not the email.
  It returns a one-time code; re-run the password grant with that `code`.
  Use the same httpx client throughout so the MFA cookie carries over.
- The code is relayed through `SmsHandler`. The endpoint returns
  `sms_required`, the frontend dialog collects the code and posts it to
  `POST /platforms/beatstars/sms`, while the login coroutine waits in
  `asyncio.to_thread(get_code)`. Challenges live in memory with a 10-minute
  TTL (`_challenges.py`).
- BeatStars caps verification SMS per account per day. Hitting the cap
  returns a 401 with "Maximum number of messages sent today was reached",
  which is shown as "try tomorrow", not as a credentials error. **Connect
  attempts are scarce; test sparingly.**

**Upload:**
1. `AddTrack`.
2. Per file: `createAssetFile` → `GET uppy-v4/s3/params` → multipart `POST`
   to `bts-content.s3-accelerate.amazonaws.com`.
3. **Wait for processing** (`_wait_until_processed`): poll the asset listings
   until `size > 0`, all files in parallel, 300 s cap. Attaching earlier
   records a 0-byte asset and the publish fails with "There are errors in
   your request".
4. `attachStream` / `attachMainAudio` / `attachStems` / `attachArtwork`. One
   MP3 can be both the stream and the main audio.
5. `SaveTrackForm` → `PublishTrackForm`.

**Rules learned from the first live run** (don't regress these):
- **Genre is required to publish.** `_resolve_genres` runs before any upload.
  It uses the user's pick if it matches the live enum
  (`GetMetadataProperties`), else the account's saved defaults
  (`fetchTrackPreference`), else fails with a clear error. Unknown labels are
  skipped, never guessed.
- **`releaseDate` comes from BeatStars' clock** (the HTTP `Date` header via
  `_clock_skew`). A fast PC clock otherwise schedules the track hours in the
  future.
- Licenses are sent as `contracts[]` of
  `{itemId, contractId, price, enabled, offerOnly}`. Contract IDs are
  per-account (fetched live through `GetTrackFormContracts`). `contracts[]`
  is the explicit enabled set, and Basic is never sent (it's the account
  default). `freeDownloadSettings: {enabled: false}` is fine.
- `PublishTrackForm` errors carry no field detail. To debug, query the draft
  with `GetTrack` and read `bundle.{progress,error,errorPart}`. Full GraphQL
  error payloads are logged at WARNING.

Tests: `tests/test_beatstars_http.py` runs against an httpx `MockTransport`
that models asynchronous asset processing.

### BeatStars over Playwright (`beatstars.py`, fallback only)

This is the legacy DOM-driven flow, kept in case the HTTP API changes. It
mirrors the HTTP path: two-step login, SMS 2FA through the same
`SmsHandler`, then the Uppy upload, the form, cover art, license toggles and
publish. The refreshed `storage_state` is persisted after each upload.
Selectors are pinned to `data-qa` / `data-cy` / IDs / visible text, never
Angular's `_ngcontent-*` classes. Traps in this flow:
- Uppy's image editor and BeatStars' Cropper.js modal intercept clicks.
  Dismiss them first (`_close_cropper_if_open`).
- Material `mat-slide-toggle` only reacts reliably when you click the hidden
  `<input role="switch">` through `page.evaluate`.
- License cards stay `.disabled.prevent-enabling` until files finish
  processing.
- The genre chip input disables itself at 3/3. `_set_chip` then does nothing
  on purpose.
- Failures write a screenshot and HTML to `storage/diagnostics/`. These hold
  logged-in DOM, so treat them as sensitive.
- The SMS-page selectors were never checked against a real challenge.

## Upload pipeline

`backend/app/api/uploads.py` + `backend/app/services/jobs.py`.

One `UploadJob` per beat, with up to five files. Per-role extensions and size
limits are in `services/storage.py::ROLE_LIMITS`:

| Role | Extensions | Limit |
|---|---|---|
| `tagged` | `.mp3` | 100 MB |
| `master` | `.wav .wave .flac` | 250 MB |
| `stems` | `.zip .rar` | 1 GB |
| `artwork` | `.png .jpg .jpeg .webp` | 10 MB |
| `video` | `.mp4 .mov .webm .m4v` | 2 GB (YouTube only) |

The UI requires the tagged MP3, since the Basic license and BeatStars publish
depend on it. The API only requires at least one audio or video file.
`save_upload` streams to disk with a running byte count, aborts once over the
limit, and deletes the partial file. Stored filenames are sanitized.

**Flow:**
1. `POST /api/uploads` (multipart files + JSON `metadata`) creates the job
   (`queued`) and stores the `UploadCreate` payload as `payload_json`. Files
   go to `storage/{user_id}/{job_id}_{role}_{filename}`.
2. `start_job` spawns an `asyncio` task, kept in `_in_flight` so it isn't
   garbage-collected. **There is no worker queue, so a process exit loses
   in-flight jobs.**
3. For each target, `connector.upload(...)` runs. `progress_cb` hops from the
   worker thread back to the loop with `run_coroutine_threadsafe` and writes
   `job.targets[provider].progress`, throttled to changes of 5% or more.
4. Any success creates a `Beat` row linked through `beat_id`. A
   `handle.session_data` result is encrypted and written back to the
   connection.
5. The frontend polls `GET /api/uploads` every 2 s while any job is queued or
   uploading.

`POST /api/uploads/{id}/retry` re-runs from `payload_json` and reuses the
files on disk. Deleting a job deletes all of its files.

YouTube description: the per-upload `description`, else the user's
`youtube_description_template`, else a built-in BPM/key blurb.

## Frontend

- **Two builds from one codebase.** `lib/target.ts::IS_DESKTOP` is
  `import.meta.env.MODE === "desktop"`.
  - **Website** routes: `/`, `/early-access`, `/privacy`, `/terms`, and
    everything else redirects to `/`. It runs Vercel Web Analytics
    (`<Analytics />` in `main.tsx`).
  - **Desktop** routes: `/dashboard`, `/upload`, `/platforms`, `/library`,
    `/settings`, and everything else redirects to `/dashboard`. It hides
    sign-out, the verify-email banner, and the account/security/danger-zone
    settings. **No analytics.**
  - The hosted account pages (login, reset, verify, Google callback) are
    still in `src/pages` but no route uses them.
- `lib/api.ts` is the only module that calls the backend. On desktop,
  `authHeaders()` sends `X-Beatuploader-Session`, read from the
  `<meta name="beatuploader-session">` tag. Types in `lib/types.ts` are kept
  in sync with the Pydantic schemas by hand.
- Data fetching uses TanStack Query (30 s `staleTime`). Mutations invalidate
  their query keys.
- `<AuthedImage>` fetches auth-protected images (artwork thumbnails) as blob
  URLs. The upload page sorts dropped files into roles by extension
  (`classify()` in `pages/upload.tsx`).
- Nav items are defined in both `components/sidebar.tsx` and
  `components/mobile-nav.tsx`.

**Two visual languages:**
- **The app** is dark and restrained, in the style of Vercel or Linear:
  zinc-950 base, monochrome, and colour only to signal state. `.lift` adds
  the card hover and `.glass` is for sticky surfaces. Easing is
  `cubic-bezier(0.32, 0.72, 0, 1)`. Animation uses the `motion` package
  (`motion/react`). The sidebar's sliding pill uses
  `layoutId="sidebar-pill"`.
- **The website** is a light cut-paper collage:
  - Generated posterized skies (`lib/collage-sky.ts`: seeded noise on a
    canvas, no image assets).
  - White paper panels with ink outlines.
  - Bodoni Moda (low `opsz`) with Zen Kaku Gothic New.
  - CSS-drawn Windows 98 dialogs.

  Styles live in `pages/landing.css`, scoped under `.landing`. The shared
  header, footer and sky live in `components/site-chrome.tsx`. The brand
  mark is the wave (`public/logo-wave.svg`). Desktop icons are generated from
  `desktop/src-tauri/app-icon.svg` with `npx tauri icon`.
- **Landing page switches:**
  - `DOWNLOAD_ENABLED` in `pages/landing.tsx`: while `false`, the download
    buttons read "Coming soon".
  - `VITE_DOWNLOAD_URL` (defaults to the fixed-name release asset).
  - `VITE_DONATE_URL`: the donate links are hidden while it's unset.

## Data model

`backend/app/models/`. Everything cascades from `User`.

```
User          email, handle, password_hash?, google_sub? (unique),
              email_verified_at?, password_changed_at?,
              youtube_description_template?, plan, created_at
PlatformConnection
              user_id, provider, status, account_label,
              access_token_encrypted   OAuth access token
              refresh_token_encrypted  OAuth refresh token
              session_data_encrypted   BeatStars session JSON (or Playwright storage_state)
              expires_at, connected_at, last_error
UploadJob     user_id, beat_id?, filename, storage_path (master),
              tagged/stems/artwork/video_storage_path, size_bytes, progress,
              status, license_type (AUTO|EXCLUSIVE|PREMIUM_PLUS|PREMIUM|UNLIMITED),
              genre, description, targets JSON {provider: {status, progress,
              external_id, public_url, error}}, payload_json, error
Beat          user_id, title, bpm, music_key, tags, price_cents, plays,
              platform_statuses JSON, released_at
WaitlistSignup  email (normalized, unique) — hosted only
```

Credentials are never stored in plain text. Every token goes through Fernet.
SQLAlchemy doesn't reliably notice in-place changes to a JSON column, so
always reassign it (`job.targets = dict(targets)`). SQLite drops tzinfo on
round-trip, so compare datetimes only after coercing naive values to UTC.

## Security model

**Desktop:**
- The backend binds only to 127.0.0.1. `LocalSessionMiddleware` rejects any
  `Host` other than `127.0.0.1:<port>` / `localhost:<port>`, which blocks DNS
  rebinding.
- Every `/api/*` request needs `X-Beatuploader-Session`, compared in constant
  time. The OAuth callbacks are exempt because their signed `state` is the
  credential.
- The token reaches only the app's own page (injected into `index.html`).
  The served UI has **no Tauri IPC**; only the bundled splash does.

**Both modes:**
- Platform tokens are Fernet-encrypted at rest, and the key is used as-is
  (never padded or derived). `decrypt_token` wraps failures in a clean
  `RuntimeError`.
- `PlatformOut` never exposes `*_encrypted` fields.
- Error responses never include exception text. Log with `log.exception`
  and return a generic message.
- Every user-controlled string has a `max_length`. Uploads are checked
  against an extension allowlist and a per-role size limit.
- `SecurityHeadersMiddleware` sends nosniff, `X-Frame-Options: DENY`, the
  referrer policy and the permissions policy. HSTS is added only when
  `DEBUG=false`.
- OAuth `state` JWTs carry a `purpose` (`signin` with no user ID, or
  platform-connect with `uid`), a nonce and a short `exp`. That makes them
  the CSRF token for redirect flows.

**Hosted only:**
- bcrypt is called directly, not through passlib (its bcrypt backend is
  broken), with input truncated to 72 bytes.
- The password policy (8–128 characters, upper, lower, digit, symbol) is
  enforced in `schemas/user._validate_password` and mirrored in
  `lib/password.ts`. Login doesn't re-check complexity, so older passwords
  still work, but it does cap the length.
- Login runs in constant time against `_DUMMY_PASSWORD_HASH`, so response
  timing doesn't reveal which emails exist.
- Changing the password stamps `password_changed_at`, and any JWT whose `iat`
  is older is rejected. Don't remove `iat`.
- JWTs are HS256 with a 7-day lifetime and the user ID as `sub`.
- The JWT is stored in `localStorage`, which is a known XSS trade-off. It's
  acceptable while there's no `dangerouslySetInnerHTML` and no third-party
  scripts.
- The Google sign-in callback returns the token in the URL fragment, which
  never reaches server logs.
- CORS uses explicit origins only; never `*` together with credentials.

## Hosting & infrastructure

| Piece | Where | Notes |
|---|---|---|
| Website | Vercel (Hobby), root `frontend/` | `www.beatuploader.app` is primary and the apex redirects to it. Web Analytics must be enabled in the Vercel project. |
| Installer + update feed | GitHub Releases | Built by `desktop-release.yml`. |
| Hosted API (legacy) | Render free web service `beatuploader-api` (Docker, Oregon) | `api.beatuploader.app` |
| Hosted DB (legacy) | Neon Postgres, project `misty-voice-04631137`, branch `production`, db `neondb`, `us-west-2` | Linked through `.neon` (gitignored). Policy in `neon.ts` (currently empty). |
| Email | Resend, domain verified | Hosted transactional mail. |
| `hello@beatuploader.app` | Cloudflare Email Routing → owner's Gmail; Gmail "Send mail as" over Resend SMTP | Contact address on the site and legal pages. |
| DNS | Cloudflare, every record **DNS-only (grey cloud)** | Proxying breaks Vercel/Render TLS and OAuth redirects. |

Infra details that matter:
- **Neon direct host, not `-pooler`.** The pooled endpoint is PgBouncer in
  transaction mode, which breaks asyncpg's prepared-statement cache. Render's
  `DATABASE_URL` is set by hand in the dashboard. Neon compute scales to zero
  after about 5 minutes; `pool_pre_ping=True` absorbs the dropped connection.
- **`db._async_database_url`** rewrites `postgres(ql)://` to
  `postgresql+asyncpg://` and strips libpq-only parameters. SSL is chosen by
  host shape:
  - single-label (Render-internal) → TLS without verification;
  - public host with a TLD → `ssl=True`;
  - localhost → no SSL.
- **Docker image:** `mcr.microsoft.com/playwright/python:v1.49.0-noble`,
  because the code needs Python 3.11 or newer (`datetime.UTC`). Playwright is
  pinned `>=1.49,<1.50` to match the image's Chromium, so bump the two
  together. The Dockerfile copies `app/` before `pip install -e .`. Uvicorn
  runs with `--proxy-headers`.
- **Render free tier** has no persistent disk, so uploads and retry-from-disk
  don't survive a restart. It doesn't support `preDeployCommand`, so
  migrations run on boot. On a paid plan, set `RUN_MIGRATIONS_ON_BOOT=false`
  and use `preDeployCommand: python -m app.migrate`.
- **DNS records:**
  - The apex and `www` are CNAMEs to Vercel's
    `0e7c0125f56bc87c.vercel-dns-017.com`, and `api` is a CNAME to
    `beatuploader-api.onrender.com`.
  - MX `route1-3.mx.cloudflare.net` (Cloudflare Email Routing; the rule
    forwards `hello@` to Gmail).
  - Apex SPF `include:_spf.mx.cloudflare.net`. Resend's SPF and DKIM were
    configured automatically.
  - DMARC `_dmarc` TXT `v=DMARC1; p=none; rua=mailto:hello@beatuploader.app`.
- **Gmail "Send mail as"** uses `smtp.resend.com:465` (SSL), user `resend`,
  with its own sending-only key named `gmail-send-as` (separate from
  Render's). If sends hang with nothing in Resend's log, the key was rotated:
  re-enter it under Gmail → Accounts and Import → Send mail as.

Step-by-step deployment: `DEPLOY.md`.

## Hosted mode (legacy)

Hosted mode is the default when `LOCAL_MODE` is unset: a multi-user API with
JWT auth on Postgres. It's still deployed, but **the website no longer links
to it, and new features shouldn't be built on hosted-only paths** (accounts,
email, Google sign-in). The one hosted feature in active use is the website's
early-release waitlist (`POST /api/waitlist`, `GET /api/waitlist/count`).

Hosted mode adds:
- **Accounts:** email + password register and login, email verification
  (7-day JWT, `purpose=email_verify`, never blocks sign-up), password reset,
  password change, and account deletion (requires typing the handle).
- **Google sign-in:** one Google consent covers sign-in and YouTube. The
  callback matches the user by `google_sub`, then by email. It also upserts
  the YouTube `PlatformConnection`, then redirects with the token in the URL
  fragment.
- **YouTube connect:** a full-page redirect instead of the system browser.
  The callback redirects to `${FRONTEND}/platforms?status=connected`.

**Google Cloud setup:** enable YouTube Data API v3.
- Consent scopes: `youtube.upload`, `youtube.readonly`, and for hosted
  sign-in `openid email profile`.
- The hosted client is a **Web application** with redirect URIs
  `{BACKEND_BASE_URL}/api/auth/google/callback` and
  `{BACKEND_BASE_URL}/api/platforms/youtube/callback`.
- The desktop client is a separate **Desktop app** client.
- The app is in **Testing** mode: only listed test users can connect, and
  refresh tokens expire after 7 days.
- Common errors:
  - `access_denied` → the account isn't a test user.
  - `redirect_uri_mismatch` → the URI differs, possibly only by a trailing
    slash.
  - no refresh token → `prompt=consent` is missing (`start_authorize` already
    forces it).

## Known gaps

Roughly by impact.

- **Google OAuth verification.** Until it's done, YouTube only works for
  test users and needs reconnecting weekly. The review takes about 4–6 weeks.
- **Real YouTube upload from the desktop app.** Not yet confirmed live.
- **Windows code signing.** The installer is unsigned, so SmartScreen warns
  on first install.
- **`VITE_DONATE_URL`** isn't set in Vercel, so the donate links are hidden.
- **No worker queue.** An app or process exit loses in-flight uploads.
  Candidates: arq, RQ, Celery.
- **More platforms.** SoundCloud needs credentials. Spotify (via DistroKid),
  Audiomack and Bandcamp aren't started.
- **macOS build.** Tauri and PyInstaller both support it, but the shell's
  dev path assumes `.venv/Scripts`.
- **FL Studio export-folder watcher** in the tray process.
- **Hosted only:**
  - The rate limiter is in-memory; swap in a Redis-backed one before
    running multiple workers.
  - Files sit on local disk; they'd need R2/S3 to scale.
  - Sessions should be HttpOnly cookies if user-rendered HTML ever ships.
  - Billing: `User.plan` exists but nothing enforces it.
