# Beatuploader

Multi-platform beat upload SaaS. Producers connect their accounts (BeatStars, YouTube, etc.) and push beats to every platform from one dashboard. Target users: independent producers selling beats.

## Layout

```
beatuploader/
├── frontend/   Vite + React 19 + TS + Tailwind v4 + motion + TanStack Query
└── backend/    FastAPI + async SQLAlchemy 2.0 + Pydantic v2 + Playwright (sync)
```

Frontend talks to backend via `/api/*` over JSON (multipart for uploads). Auth is JWT Bearer in `Authorization` header, token in `localStorage`.

## Production (LIVE as of 2026-05-25)

Deployed and serving real traffic:

- **Frontend**: `https://beatuploader.app` (+ `www.`) on **Vercel** (free Hobby plan). Root dir `frontend/`, env `VITE_API_BASE=https://api.beatuploader.app/api`. `www` is primary, apex 307-redirects to it (flip in Vercel → Domains → Set as Primary if you want apex canonical).
- **Backend**: `https://api.beatuploader.app` on **Render** (free web service, Docker). Service name `beatuploader-api`, region oregon.
- **DB**: **Neon** free Postgres — project `misty-voice-04631137`, branch `production`, db `neondb`, region `us-west-2`. The repo is linked via `.neon` (gitignored); `neon link` / `neon deploy` refresh `.env.local` with `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `NEON_BRANCH`. Render's `DATABASE_URL` is set **manually in the dashboard** (`sync: false`) to the **direct** Neon host — the one WITHOUT `-pooler`. The pooled endpoint is PgBouncer in transaction mode, which breaks asyncpg's prepared-statement cache unless you also pass `statement_cache_size=0`; we run one instance with SQLAlchemy's own pool, so direct is correct. Neon compute scales to zero after ~5 min idle — `pool_pre_ping=True` in `db.py` absorbs the dropped connections. Config-as-code policy lives in `neon.ts` (`neon config plan` to preview, `neon deploy` to apply); it is currently an empty `defineConfig({})`, i.e. no overrides. Migrated off Render free Postgres (`beatuploader-db`, deleted after 90 days) on 2026-09-15; the `databases:` block is gone from `render.yaml`. ⚠️ The Neon branch started **empty** — schema is created by `init_db()` on first boot, and no data was carried over from the old Render DB.
- **Email**: Resend, domain `beatuploader.app` verified (SPF/DKIM via Cloudflare auto-config). SMTP creds in Render env. End-to-end verified — register/verify/reset emails arrive.
- **DNS**: Cloudflare, all records **grey-cloud (DNS-only)** — Vercel/Render do their own TLS, proxying breaks cert issuance + OAuth redirects. Three CNAMEs: apex + www → Vercel's `0e7c0125f56bc87c.vercel-dns-017.com`, `api` → `beatuploader-api.onrender.com`.
- **Google OAuth**: prod redirect URIs + JS origins added (sign-in + YouTube). App still in Testing mode — non-owner users need adding as test users until Google verification (4-6wk).
- **Runbook**: `DEPLOY.md`. Deploy infra config: `render.yaml`, `frontend/vercel.json`.

**Verified working in prod**: email/password register + login, email verification, password reset, Google sign-in (+ auto YouTube connect), CORS. **NOT yet verified in prod**: a real YouTube upload (do this), a real BeatStars upload via the new HTTP connector (do this — see below).

### BeatStars now runs over its private HTTP API (free-tier unblocked)

BeatStars connect/upload was **reverse-engineered from the studio.beatstars.com web client** (HAR capture, May 2026) and reimplemented over plain HTTP with `httpx` — **no browser**. This unblocks Render free tier: no Chromium = no 512MB OOM, no CPU starvation. The protocol turned out to be clean — standard OAuth2 + GraphQL + S3 presigned POST, **no captcha on the API, no tus**:

- **Auth**: `POST core.prod.beatstars.net/auth/oauth/token` `grant_type=password` (+ an `identifierAvailable` GraphQL check for a clean "no account" error). Refresh via `grant_type=refresh_token`; re-login with the stored password if refresh fails. The OAuth client id/secret are baked into BeatStars' own frontend (effectively public, not user secrets).
- **Upload**: `AddTrack` → per-file `createAssetFile` → `GET uppy-v4/s3/params` → multipart `POST` to `bts-content.s3-accelerate.amazonaws.com` → `attachStream`/`attachMainAudio`/`attachStems`/`attachArtwork` → `SaveTrackForm` → `PublishTrackForm`. Licenses are a `contracts[]` of `{itemId, contractId, price, enabled, offerOnly}`; contract ids are **per-account** (fetched live via `GetTrackFormContracts`). Genres resolved against the live enum (`GetMetadataProperties`) — unknown labels are skipped, never guessed (a bad enum would fail the publish).

Code: `services/platforms/_beatstars_http.py`. `beatstars.py::BeatStarsConnector` dispatches to it when **`BEATSTARS_USE_HTTP=true` (the default)**; set `false` to fall back to the legacy Playwright flow (kept as a safety net). The HTTP path is **transport-only** — the credentials/SMS API endpoints, `connect_with_credentials`'s `(password_enc, session_enc, label)` contract, and the job pipeline are all unchanged (the persisted "session" is just `{access_token, refresh_token, expires_at, member_id, account_label}` JSON instead of Playwright storage_state).

**Verified**: 12 unit tests (`tests/test_beatstars_http.py`) exercise the full upload + login (incl. 2FA) against an httpx `MockTransport`. **Login confirmed live** (creds accepted, 2FA fires); a full live connect + upload is still pending the SMS-cap reset (below). Assumptions to watch if a live publish 400s:
1. `freeDownloadSettings: {enabled: false}` — we send the minimal shape; the captures only ever showed it enabled with a full `terms` block. If rejected, send the full object (`_FREE_DOWNLOAD_OFF` in `_beatstars_http.py`).
2. MP3-only uploads attach the one MP3 asset to **both** `attachStream` and `attachMainAudio` (the capture had a separate WAV master).
3. `contracts[]` is treated as the explicit enabled-set; we never send Basic (the captures never did — Basic is the account default).

**SMS 2FA — required from server IPs, and implemented** (`_beatstars_http._complete_mfa`). Logins from Render's datacenter IP reliably trigger BeatStars SMS 2FA (new-device detection); home/browser logins don't, so no HAR captured it — the flow was recovered from the login JS bundle. Mechanics:
- Plain password grant **auto-sends the SMS** and returns error code `MFA_VERIFICATION_ACTION`.
- Verify is a GraphQL mutation on `/auth/graphql`: `verifyMfa({verifyMfaRequest:{identifier, pin}})` — `pin` is the SMS code; `identifier` is the **resolved BeatStars username** (`profileDetails.username` from `identifierAvailable`, **NOT** the email used for the grant). It returns a one-time code; re-run the password grant with it as `code` to get tokens. Same httpx client throughout so the MFA cookie carries.
- Relayed through the existing `SmsHandler` + `/platforms/beatstars/sms` endpoint + frontend dialog (unchanged): `on_detected` → endpoint returns `sms_required`; the login coroutine blocks on `asyncio.to_thread(get_code)` until the code arrives.
- **Daily SMS cap**: BeatStars limits verification SMS per account/day; exhausting it returns 401 `"Maximum number of messages sent today was reached"` (detected + surfaced as a clear "try tomorrow", NOT a creds error). Connect attempts are a scarce daily resource — iterate sparingly. Normal use is unaffected: once connected, uploads reuse the refresh_token (no re-login, no SMS).

### ⚠️ Temporary `[diag]` debug code in `_beatstars_http.py` — REVERT after one clean connect

To debug the live 2FA flow under a scarce daily SMS budget, `_beatstars_http.py` currently surfaces raw error detail to the client in two spots (both marked `# TEMP DIAGNOSTIC`): the `verifyMfa` rejection (`[diag] verifyMfa rejected (identifier=...)`) and any non-MFA 400/401 grant body (`[diag] grant HTTP ...`). These leak response bodies — **revert to the generic messages once a real connect succeeds.**

### Debug commits reverted

The two temporary OOM-diagnosis commits are reverted (commit `513d4e7`): `/platforms/beatstars/credentials` no longer leaks exception internals in its 500 (back to the generic message), and the Chromium `--single-process`/`--no-zygote` flags are gone (kept the harmless `--disable-dev-shm-usage`/`--disable-gpu`). Moot for the default HTTP path anyway — it launches no browser. `*.har` network captures are gitignored (they carry live tokens/passwords).

## What works today

- **YouTube** — OAuth connect + auto-upload of the master/tagged audio as an unlisted video. Token auto-refresh persists the new access token back to the DB (`7825e32`). End-to-end working **in dev**; prod-verify a real upload.
- **BeatStars** — **HTTP/GraphQL connector** (`_beatstars_http.py`, the default) — password-grant login **+ SMS 2FA** (via `verifyMfa`), full upload (assets→S3→attach→save→publish), license/price selection, genre-enum resolution. Runs on free-tier hosting (no browser). **Unit-tested + login confirmed live; full connect+upload pending the SMS-cap reset.** Legacy Playwright path (headless login + SMS 2FA + DOM-driven upload, cover art + license picking) kept behind `BEATSTARS_USE_HTTP=false`. See "Production → BeatStars now runs over its private HTTP API" above.
- **SoundCloud** — **OAuth2 connector built** (`soundcloud.py`): authorization-code + PKCE via `secure.soundcloud.com`, multipart upload to `api.soundcloud.com/tracks`, token refresh. Wired (registry + `/soundcloud/callback`). **Blocked on credentials, NOT code** — registering an app needs an active **Artist Pro** account; once `SOUNDCLOUD_CLIENT_ID`/`SECRET` are set it's connectable. Our use case is explicitly permitted by SoundCloud's API terms ("sale of an app with an Upload integration" + "promote content via authenticated access to the user's account"). Unit-tested against a mock transport; **not yet verified against the live API** (auth-header scheme `OAuth` vs `Bearer`, `/tracks` field names — iterate once creds exist).
- **Spotify / Audiomack / Bandcamp** — enum entries only, no connector files yet.

## Run dev

Easiest: from repo root, `./start.ps1` spawns both servers in separate PowerShell windows and gives you a `restart` / `kill` prompt in the parent. See `start-backend.ps1` (uvicorn on **port 8001**) and `start-frontend.ps1` (Vite). Closing the parent terminal triggers the `finally` block which kills both.

Manual:
```powershell
# Backend
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8001     # http://localhost:8001  (docs at /docs)

# Frontend
cd frontend
npm run dev                                    # http://localhost:5173
```

**First-time setup:**
- Backend venv: `python -m venv .venv && .venv\Scripts\python.exe -m pip install -e .`
- Playwright: `playwright install chromium` (~150MB)
- DB: created/migrated automatically on first boot via `init_db()` (runs `alembic upgrade head`), gated by `RUN_MIGRATIONS_ON_BOOT` (true in dev and on current free-tier prod). On a paid Render plan, switch to `RUN_MIGRATIONS_ON_BOOT=false` + `preDeployCommand: python -m app.migrate` — see "Pitfalls / Alembic migrations on boot" and `render.yaml`.

**Current dev setup runs on port 8001**, not 8000 — hardcoded in `start-backend.ps1`. There's no `backend/.env` — the user is running on **all dev defaults**. `BACKEND_BASE_URL=http://localhost:8001` is needed for OAuth redirect URIs to line up; `frontend/.env.local` has `VITE_API_BASE=http://127.0.0.1:8001/api`. Why 8001 in the first place: Windows leaves zombie LISTENING entries on 8000 for many minutes after a hard kill. If you change the port, update `start-backend.ps1`, the env override, `frontend/.env.local`, and the Google Console redirect URIs together.

**To set up real secrets** before deploying or going to prod mode:
```powershell
# JWT secret (>= 32 chars)
python -c "import secrets; print(secrets.token_urlsafe(48))"
# Fernet key for platform tokens
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Put both in `backend/.env` alongside `DEBUG=false`. In `DEBUG=true` (default), weak/missing secrets log a warning and boot proceeds; in `DEBUG=false` they raise at startup. See "Security model" below.

## Architecture

### Platform connector abstraction (`backend/app/services/platforms/`)

Every upload target implements `PlatformConnector` (`base.py`). Provider-agnostic API layer — adding a platform is one file with 5 methods.

```
PlatformConnector
├── start_authorize(user_id, redirect_uri) → OAuthRedirect  # OAuth-only
├── complete_authorize(code, state, redirect_uri) → dict    # OAuth-only
├── disconnect(connection)
├── upload(connection, file_path, meta) → UploadHandle
└── poll(connection, handle) → UploadProgress               # status checks
```

**`AuthMethod`** distinguishes connection style:
- `oauth` — YouTube (Google Data API v3, working end-to-end)
- `headless` — BeatStars (Playwright-driven, working end-to-end)
- `api_key` — preset token (unused)

**Registry** is in `registry.py`. Currently wired: `youtube`, `beatstars`, `soundcloud` (the last needs `SOUNDCLOUD_CLIENT_ID`/`SECRET` to actually connect). Other providers in `PlatformProvider` enum (spotify, audiomack, bandcamp) aren't even stubbed yet — adding any of them just requires a file and registry entry.

**`PlatformConnector.is_configured()`** (default `True`) reports whether a connector has the operator-provisioned credentials it needs. OAuth connectors override it (`bool(get_settings().<provider>_client_id)`); headless BeatStars stays `True`. The `/platforms` list surfaces it as `PlatformOut.configured`, and the frontend shows un-configured platforms as **"Coming soon"** (disabled) rather than a Connect button that errors — so SoundCloud sits dormant cleanly until its creds are set. Frontend treats a *missing* `configured` as available (only an explicit `false` = coming soon), so a backend deploy lag never hides a working platform.

### Upload pipeline (`backend/app/api/uploads.py` + `services/jobs.py`)

Multi-file model. Each upload is one `UploadJob` with up to four files:

| Role     | Required | Extensions          | Per-role size limit |
|----------|----------|---------------------|--------------------|
| `tagged` | **Yes**  | `.mp3`              | 100 MB             |
| `master` | optional | `.wav .wave .flac`  | 250 MB             |
| `stems`  | optional | `.zip .rar`         | 1 GB               |
| `artwork`| optional | `.png .jpg .jpeg .webp` | 10 MB         |

MP3 is the required file (Basic license uses it; BeatStars can't publish without it). Limits enforced in `services/storage.py::save_upload` — mid-stream abort + partial-file cleanup if exceeded.

**Flow:**
1. Frontend `POST /api/uploads` with multipart form: optional `master/tagged/stems/artwork` + JSON `metadata`
2. Backend creates `UploadJob` (status=queued), stores `UploadCreate` payload as `payload_json` (used for retry), streams each file to `./storage/{user_id}/{job_id}_{role}_{filename}`
3. `start_job(job_id, user_id, payload)` spawns an asyncio task (held in `_in_flight: set[Task]` so GC doesn't reap it)
4. Task iterates `job.targets`, calls `connector.upload(connection, file_path, meta)` for each
5. On any success: creates a `Beat` row (links to job via `beat_id`), persists per-target status in `job.targets` JSON
6. If `handle.session_data` came back (BeatStars), encrypt + persist to `connection.session_data_encrypted` — keeps the next upload's session warm
7. Frontend polls `GET /api/uploads` every 2s while any job is `queued`/`uploading`

**Retry:** `POST /api/uploads/{id}/retry` resets status + targets and re-runs from the stored `payload_json`. Disk files (master/tagged/stems/artwork) are reused.

**Job deletion** cleans up all four file roles on disk before deleting the row.

**Background processing is asyncio.create_task — NOT Celery/RQ.** Fine for MVP. Process crash = in-flight jobs lost. Revisit when multi-user or you need retries/scheduling.

**Progress reporting:** `PlatformConnector.upload` takes an optional `progress_cb: Callable[[int], None]`. `jobs.py` supplies a thread-safe callback that uses `asyncio.run_coroutine_threadsafe` to hop from the connector's worker thread back to the loop, write `job.targets[provider].progress`, and commit. Throttled to >=5% deltas so a fast link doesn't spam the DB. **YouTube wired** (via `MediaUploadProgress.progress()` per chunk). BeatStars accepts the callback but doesn't use it yet — Uppy emits progress events; wiring them is a future cleanup.

### Auth (`backend/app/api/auth.py`, `frontend/src/lib/auth.tsx`)

Three sign-in surfaces, all issue the same Beatuploader JWT:

1. **Email + password**: `POST /api/auth/register`, `POST /api/auth/login`. Race on register caught (`IntegrityError` → 409).
2. **Google sign-in**: `POST /api/auth/google/start` returns a Google authorize URL with scopes `openid email profile youtube.upload youtube.readonly`. After approval → `GET /api/auth/google/callback` → verify ID token, match by `google_sub` then auto-link by email, create user if neither, **also upsert the YouTube `PlatformConnection`** from the same token exchange. Redirects to `${FRONTEND}/auth/google#token=<jwt>` (URL **fragment** — never hits server logs).
3. (Headless) BeatStars credentials: `POST /api/platforms/beatstars/credentials` with username/password. Validates by logging in via Playwright, captures cookies, encrypts + persists. Different from sign-in — doesn't issue a Beatuploader JWT.

**User model nuances:**
- `password_hash` is nullable (Google-only users don't have one). Login rejects when `password_hash is None`.
- `google_sub` is a nullable unique index.
- `email_verified_at` is nullable. Set immediately on Google sign-in (Google has already verified the email). Set on email/password registrations by the verify-email flow.

**Email verification flow:**
- Register sends a 7-day JWT (`services/email_verification.py`, `purpose=email_verify`) over SMTP via the existing `send_email` service. SMTP failures don't fail registration — `send_email` swallows errors so a misconfigured SMTP doesn't block sign-up.
- `POST /api/auth/verify-email {token}` (unauthenticated; the token is the credential) stamps `email_verified_at`. Re-verifying with the same token is a no-op success rather than an error.
- `POST /api/auth/resend-verification` (authed, rate-limited 3/5min) re-sends or short-circuits if already verified.
- Frontend renders a dismissible `<VerifyEmailBanner />` inside the dashboard layout. **Not blocking** — test users shouldn't be locked out by an SMTP misconfig. Re-enable gating later if/when needed.
- `lib/auth.tsx` exposes `refresh()` so the verify-email page can clear the banner after success without a full page reload.

**Settings:**
- `PATCH /api/auth/me` — change handle (email change is intentionally not supported)
- `POST /api/auth/change-password` — change password. Requires `current_password` unless user has none (Google-only setting one for the first time).
- `DELETE /api/auth/me` — delete account. Body `{confirm_handle}` must match. Cascades platforms/uploads/beats/files.

**Common code:**
- `deps.py::get_current_user` decodes JWT, catches `ValueError` (bad token) and `(TypeError, ValueError)` from `int(sub)` → 401. SQLite drops tzinfo when round-tripping `DateTime(timezone=True)`; we coerce naive `password_changed_at` values to UTC before comparing against the iat — without this, dev (SQLite) crashed on the comparison.
- Frontend `lib/auth.tsx` hydrates user via `GET /api/auth/me` on mount; `setUnauthorizedHandler` clears token on any 401 → kicks to `/login`
- Sign-in OAuth state JWT carries `purpose=signin` (no user_id); platform-connect state carries `uid`. Don't confuse them in callbacks.

### Per-platform OAuth (e.g. YouTube)

Distinct from sign-in. For YouTube:
1. Frontend `POST /api/platforms/youtube/connect` → returns `authorize_url` (signed state JWT embeds `user_id`)
2. Frontend redirects to Google
3. Google → `GET /api/platforms/youtube/callback?code=&state=` → verify state, exchange code, encrypt tokens via Fernet, upsert `PlatformConnection`, 302 to `${FRONTEND}/platforms?status=connected&provider=youtube`
4. Frontend reads URL params on mount, shows banner, refetches platforms

Redirect URI is computed from `BACKEND_BASE_URL` in `.env` — must match exactly what's registered in Google Console.

### BeatStars (headless Playwright — now the FALLBACK)

> **This is the legacy path, used only when `BEATSTARS_USE_HTTP=false`.** The default is now the HTTP connector (`_beatstars_http.py`) — see "Production → BeatStars now runs over its private HTTP API". This section documents the Playwright fallback, kept as a safety net if the HTTP API drifts.

The hardest integration and the product's differentiator. Lives in `services/platforms/beatstars.py`. **All selectors are verified against the live UI (May 2026).**

**Auth flow** (`_do_login`):
- Two-step: email page (`#oath-email`) → click Continue → password page (`#userPassword`) → click Continue
- BeatStars redirects unknown emails to `/sign-up` — we detect this and surface "No BeatStars account found"
- SMS 2FA: when BeatStars triggers it (new device, suspicious IP), we detect `/verify`-style URLs OR known body text patterns. Resolution is interactive: `_do_login` accepts an `SmsHandler` (callbacks for `on_detected` + blocking `get_code`). The credentials endpoint races the worker task against the SMS event; on detection it returns `{status: "sms_required", challenge_id}` while the worker thread parks at the verify page (browser stays open). The frontend prompts for the 6-digit code; `POST /api/platforms/beatstars/sms` puts it on the challenge's `queue.Queue`, the worker submits it, and the SMS endpoint awaits the worker task to finish persisting the session. In-memory challenge store with 10-min TTL (`services/platforms/_challenges.py`). The 5-min `queue.get` timeout is what actually closes the browser if the user walks away.
- Login success = URL leaves `oauth.beatstars.com` for any other `beatstars.com` subdomain (homepage `www.beatstars.com` counts).

**Upload flow** (`_do_upload`):
1. Navigate to `https://studio.beatstars.com/content/tracks/uploaded?create=true` (the `?create=true` auto-opens the Uppy dialog)
2. **Dismiss the first-time onboarding carousel** if present (`bs-responsive-dialog-feature-template .close-btn-wrapper button`) — only appears once per session, but our headless session is "first time" until we persist cookies
3. Wait for `.uppy-Dashboard` to attach, then `set_input_files` on the hidden audio Uppy input with ALL audio files (master + tagged + stems). BeatStars's "smart upload" auto-categorizes by file extension.
4. Wait for `#title` to become visible (signal: file accepted, form is ready)
5. Fill title, BPM, key (`bs-select[data-qa="select_key"] select`), tags (chip input — type and press Enter)
6. **Genre is OPTIONAL** — only fill if user supplied one. BeatStars carries genres from previous track if you don't touch the field. The genre input is autocomplete-only with a 3/3 limit.
7. **Cover art** (`_upload_artwork`):
   - Click `[data-cy="artwork-drop-down-button-button"]` (Edit) → menu opens
   - Click "Upload file" menu item → new Uppy dialog with image-only input
   - `set_input_files` on `input.uppy-Dashboard-input[accept*="image"]:not([webkitdirectory])`
   - **Uppy auto-opens its built-in image editor with cropper.js** — the editor's `.cropper-modal` intercepts clicks. Click `.uppy-DashboardContent-save` to close the editor before doing anything else.
   - Wait for `button.uppy-StatusBar-actionBtn--upload:not([disabled])` (Uppy needs time to process the file before this button enables), click it
   - Close BeatStars's post-upload Cropper.js modal (`_close_cropper_if_open` — tries Save/Apply/Done/Confirm/Crop/Upload/Submit, Esc as fallback)
   - **Confirm by checking `img.track-form-artwork.src` changed** from the snapshot we took at the start — that's the only honest success signal
8. **License selection** (`pick_licenses` + `_enable_license`):
   - Rules: `MP3 only → Basic` (BeatStars auto-on, we don't touch), `MP3 + WAV → Premium + Unlimited`, `MP3 + WAV + stems → Premium + Unlimited + Exclusive`
   - `PREMIUM_PLUS` is NOT in the auto set — pick it explicitly to get it
   - License cards have `.license-card.disabled.prevent-enabling` until files are processed; we `wait_for_function` until that class is gone (up to 3 min — stems can be slow)
   - **Click the toggle via JS**, not Playwright's `.click()` on the `mat-slide-toggle` wrapper. Material's slide-toggle wraps a hidden `<input type="checkbox" role="switch" class="cdk-visually-hidden">`; clicking the outer wrapper doesn't reliably reach the input through Angular's change detection. `page.evaluate` finds the card by text and calls `.click()` on the input directly.
   - Confirm by waiting for the card to gain the `enabled` class.
   - Price (`input[data-cy="contract_price"]`) — only set if user provided a price. In `AUTO` mode the user's price applies to the **highest tier only** (Exclusive if present, else last in list); other tiers use BeatStars defaults.
9. Publish (`button[data-cy="publish_btn-button"]`)
10. Wait for share dialog (`mat-dialog-container:has-text("Share your CONTENT")`) — the success signal
11. Capture refreshed `context.storage_state()` and attach to `UploadHandle.session_data`. Job processor encrypts + persists this back to the connection so the next upload skips onboarding + re-login.

**Diagnostic capture:** any failure in login or upload writes a full-page screenshot + HTML to `./storage/diagnostics/{label}-{timestamp}.{png,html}`. Crucial for debugging selector drift.

### Models (`backend/app/models/`)

```
User
├── id, email, handle, password_hash (nullable), google_sub (nullable, unique),
│   email_verified_at (nullable), password_changed_at (nullable),
│   youtube_description_template (nullable), plan, created_at
├── platforms ←→ PlatformConnection (cascade delete)
├── uploads ←→ UploadJob (cascade delete)
└── beats ←→ Beat (cascade delete)

PlatformConnection
├── user_id, provider (PlatformProvider enum), status (PlatformStatus enum)
├── account_label                  # username for headless, channel name for OAuth
├── access_token_encrypted         # OAuth: access token | Headless: password
├── refresh_token_encrypted        # OAuth only
├── session_data_encrypted         # Headless only — Playwright storage_state JSON
├── expires_at, connected_at, last_error
└── (no plain-text creds anywhere — everything via Fernet)

UploadJob
├── user_id, beat_id (FK, nullable)
├── filename, storage_path (master), tagged_storage_path, stems_storage_path, artwork_storage_path
├── size_bytes, progress, status (UploadStatus enum)
├── license_type (string: AUTO|EXCLUSIVE|PREMIUM_PLUS|PREMIUM|UNLIMITED|None)
├── genre (string, nullable)
├── targets (JSON: {provider: {status, progress, external_id, public_url, error}})
├── payload_json (the original UploadCreate, serialized — used by retry)
└── error, created_at, updated_at

Beat
├── user_id, title, bpm, music_key, tags (JSON), price_cents, plays
├── platform_statuses (JSON: {provider: "live"|"uploading"|"failed"|"none"})
└── released_at, created_at
```

## Security model

- **Passwords** — bcrypt hashed via `security.py::hash_password`. Inputs truncated to 72 bytes (bcrypt's hard limit) before hashing/verifying. Direct bcrypt, NOT passlib (passlib's bcrypt backend is broken).
- **Password policy** — enforced server-side in `schemas/user._validate_password` (used by `UserRegister.password` and `PasswordChange.new_password`): 8–128 chars, with uppercase, lowercase, digit, and special character. Frontend mirror in `lib/password.ts` powers the inline checklist on register + change-password forms. **Login does NOT re-enforce** complexity (existing weaker passwords must still authenticate) but caps length at 128 chars to prevent oversized-payload DoS.
- **Constant-time login** — `api/auth.login` always runs `verify_password` against either the real hash or a `_DUMMY_PASSWORD_HASH` baked at import. Equalizes timing between the user-exists and user-doesn't branches → no timing-side-channel email enumeration.
- **JWT revocation on password change** — `User.password_changed_at` stamps every register + change-password. `deps.get_current_user` rejects any token whose `iat` predates that stamp. Practical effect: changing your password logs out every other session within the next request. The column is part of the baseline Alembic migration, so fresh DBs already have it.
- **Rate limiting** — in-memory sliding-window limiter in `services/rate_limit.py`. Wired on `/auth/login` (10/min), `/auth/register` (5/min), `/auth/change-password` (5/min), `/auth/google/start` (20/min), `/platforms/beatstars/credentials` (3/min), `/platforms/beatstars/sms` (5/min). Per-IP. **Single-process only** — for multi-worker deploys, swap for a Redis-backed limiter (e.g. `slowapi + limits`). Behind a reverse proxy, run uvicorn with `--proxy-headers` so `request.client.host` reflects the real source.
- **Security headers** — `main.SecurityHeadersMiddleware` applies `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy` denying geo/mic/cam/usb/payment. HSTS (`max-age=31536000; includeSubDomains`) is added only when `DEBUG=false` so it doesn't pin dev's plaintext `http://localhost`.
- **Platform tokens** — encrypted at rest with Fernet (`security.py::encrypt_token`). The Fernet instance reads `TOKEN_ENCRYPTION_KEY` directly — **no silent padding/derivation**. Pre-this-audit code derived keys from short strings, which is dangerous; that's been removed. `decrypt_token` wraps any failure in a clean `RuntimeError` so we don't leak crypto internals.
- **Secret validation** — `config.py::_validate_secrets` runs at startup. In `DEBUG=true` (default) it warns; in `DEBUG=false` (prod) it raises if `JWT_SECRET` is the dev default, `< 32` chars, or `TOKEN_ENCRYPTION_KEY` isn't a valid Fernet key.
- **Error responses** — never expose raw exception text to clients. All OAuth callback/save/retry paths log the full exception server-side via `log.exception(...)` and return a generic message.
- **File uploads** — extension allowlist + per-role size limit enforced in `services/storage.py::save_upload`. Streams to disk with a running byte count; aborts mid-stream and cleans up the partial file if over the limit. Filename sanitization (`isalnum() or in "._- "`) blocks path traversal in the on-disk filename.
- **Schema length caps** — all user-controlled string fields have explicit `max_length` (notably `BeatStarsCredentials.username`/`password`, `BeatStarsSmsSubmit.code`, `UserLogin.password`, `AccountDelete.confirm_handle`, OAuth `code`/`state` query params). Prevents oversized-payload DoS before any heavy work (bcrypt, Playwright, etc.).
- **JWT** — HS256, 7-day expiry. Subject claim is the user ID (int). `iat` (issued-at) is load-bearing for the password-change revocation check above — don't strip it. State JWTs for OAuth are signed with the same secret but carry a `purpose` field to distinguish sign-in from platform-connect.
- **Token in URL fragment** (Google sign-in callback redirect) — fragments don't hit server logs (HTTP spec). Browser history is the only risk.
- **Token in `localStorage`** — known tradeoff: simpler than HttpOnly cookies but exfiltrable by any XSS. Mitigated by React's default escaping and zero `dangerouslySetInnerHTML` in the codebase. Revisit if we ever add user-rendered HTML or third-party scripts.
- **CORS** — `cors_origins` env var, comma-separated. Default localhost. **For prod: set explicitly** to the exact frontend origin(s); never use `*` with `allow_credentials=True`.
- **CSRF** — not applicable for the API (Bearer JWT, not cookies). OAuth state JWT (`purpose` + nonce + short `exp`) acts as the CSRF token for the redirect flows.
- **`PlatformOut` schema** — never exposes `*_encrypted` fields. Verified.
- **Diagnostics screenshots** — captured to `./storage/diagnostics/`. `storage/` is in `.gitignore`. These contain BeatStars's logged-in DOM; treat as sensitive.

## Frontend conventions

- `lib/api.ts` is the only place that talks to the backend. Auth header injected automatically. 401 triggers the `unauthorizedHandler` (set by `AuthProvider`) which clears the token and redirects to `/login`.
- Types in `lib/types.ts` mirror backend Pydantic schemas. Keep in sync by hand — no codegen.
- All dashboard pages use TanStack Query (`useQuery`/`useMutation`). 30s `staleTime` default. Use `qc.invalidateQueries({ queryKey: [...] })` after mutations.
- Empty/loading/error states required on every data view (see `library.tsx` for the canonical pattern).
- Use `useAuth()` for user info; don't pass user through props.
- `<AuthedImage>` (`components/authed-image.tsx`) for any endpoint that requires auth — fetches with Bearer header, returns blob URL. Used for `/api/uploads/{id}/artwork` thumbnails.
- The upload page auto-categorizes dropped files by extension (`classify()` in `pages/upload.tsx`).

**Routes:** `/` is the public landing page. The dashboard root is `/dashboard` (NOT `/`). Authed visitors who hit `/` get bounced to `/dashboard`. Public routes: `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/auth/google`, `/privacy`, `/terms`. Authed-only routes (wrapped by `AuthGate` + `Layout`): `/dashboard`, `/upload`, `/platforms`, `/library`, `/settings`. Don't link to `/` from authed pages — link to `/dashboard`.

**Mobile nav:** sidebar is `hidden md:flex`. On phones, `components/mobile-nav.tsx` renders a hamburger in the Topbar that opens a Radix Dialog sheet with the same nav items. Don't duplicate nav items — `navItems` is defined in both `sidebar.tsx` and `mobile-nav.tsx`; keep them in sync by hand if you add a new top-level page.

## Backend conventions

- Async everywhere (SQLAlchemy 2.0 async). Don't introduce sync sessions.
- Routers under `app/api/`, mounted by `app/api/router.py` under `/api`.
- Pydantic schemas in `app/schemas/` — never return ORM models directly from endpoints. Use a `_serialize` helper if you need to derive output fields (see `api/uploads.py::_serialize` for `has_artwork`).
- DB session via `DbSession = Annotated[AsyncSession, Depends(get_db)]`; current user via `CurrentUser`.

## Key design choices to preserve

- **Dark/expensive aesthetic** — Vercel/Linear vibe. zinc-950 base, monochrome, color only signals state. `.lift` for card hover, `.glass` for sticky surfaces. iOS spring easing (`cubic-bezier(0.32, 0.72, 0, 1)`). Don't add color "for fun."
- **motion library, not framer-motion** — `motion` is the rebranded package. Import from `motion/react`.
- **Sliding sidebar pill** uses `layoutId="sidebar-pill"`. Don't replace with hardcoded active styles.
- **Windows asyncio + Playwright** — Uvicorn on Windows uses `WindowsSelectorEventLoopPolicy` which doesn't support subprocesses. `app/main.py` sets `WindowsProactorEventLoopPolicy` at module top *before* any other imports. Headless connectors use **sync Playwright** wrapped in `asyncio.to_thread` (see `services/platforms/_browser.py`). Don't switch to async Playwright on Windows.
- **JSON column mutation** — SQLAlchemy doesn't track in-place dict mutation on JSON columns reliably. Always reassign: `job.targets = dict(targets)`, never `job.targets["x"] = ...`.
- **bcrypt directly, not passlib** — passlib's bcrypt backend is broken on modern bcrypt.

## Pitfalls

- **Alembic migrations on boot (current free-tier config)** — `init_db()` runs `alembic upgrade head` on every app boot, gated by `RUN_MIGRATIONS_ON_BOOT` (currently `"true"` in `render.yaml`). Render free tier **does not support `preDeployCommand`**, so we run migrations on boot. Safe because free tier is pinned to a single instance — no version-lock race. **When you move to a paid plan**, flip `RUN_MIGRATIONS_ON_BOOT=false` and re-add `preDeployCommand: python -m app.migrate` to `render.yaml` (commented guidance is in the file) to avoid multi-worker races.
- **No real worker queue** — `asyncio.create_task` lives in the process. Process crash = in-flight uploads lost. The `_in_flight` set holds references but only prevents GC; doesn't survive a restart.
- **DATABASE_URL normalization + SSL** — `app/db._async_database_url` rewrites `postgres://` and `postgresql://` to `postgresql+asyncpg://`, and strips libpq-only query params (`sslmode`, `channel_binding`, `target_session_attrs`, `gssencmode`) that asyncpg ignores. SSL is then chosen by hostname shape in `db.py`: **single-label hosts** (e.g. Render-internal `dpg-xxx-a`, no TLD) get an `ssl.CERT_NONE` context — TLS happens but cert verification is skipped, because Render's internal Postgres uses a self-signed cert (this was a real prod boot crash, fixed `67eba1a`). **Public hosts** with a TLD (Neon, Supabase, Render external URL) get `ssl=True` (full verification). Localhost/127.0.0.1 skip SSL entirely. Keep this branching if you touch `db.py`.
- **BeatStars selectors can break anytime** — Angular CSS classes (`_ngcontent-ng-c*`) change every BeatStars deploy. We pin to `data-qa`, `data-cy`, IDs, and visible text. If something stops working, capture a diagnostic and check the selectors.
- **Cropper / Uppy editor blocking** — both Uppy's built-in editor (`.uppy-DashboardContent-panel--editor`) and BeatStars's post-upload Cropper.js (`.cropper-modal`) intercept clicks. Always dismiss them before trying to click anything else. The artwork upload + license toggle paths both run `_close_cropper_if_open` defensively.
- **Material slide-toggle clicks** — `mat-slide-toggle` wraps a hidden `<input role="switch">`. Clicking the wrapper through Playwright's `.click()` doesn't reliably register with Angular's change detection. Use `page.evaluate` to call `.click()` on the input directly. See `_enable_license`.
- **Genre chips can be disabled at 3/3 limit** — BeatStars carries 3 genres over from the user's last upload. If we try to add a new genre, the input is `disabled="true"`. Our `_set_chip` no-ops silently in that case; the existing 3 stick. By design.
- **Diagnostics may leak** — `./storage/diagnostics/` contains BeatStars's logged-in DOM snapshots. `storage/` is gitignored, but don't share these casually.
- **Account-deletion JWT** — after `DELETE /api/auth/me`, the user's outstanding JWT is still cryptographically valid but `get_current_user` now 401s because the user row is gone. Frontend handles this via the 401 → logout flow.

## Known gaps / TODO

Ranked roughly by impact. Items struck from the previous version of this list have moved to "Done since last revision" below.

- **BeatStars SMS 2FA selector verification** — the interactive flow is built end-to-end (challenge store + `SmsHandler` callbacks into `_do_login` + two-stage frontend dialog). Selectors for the SMS code input (`input[autocomplete="one-time-code"]`, `input[name="code"]`, etc.) and submit button are best-guesses since the 2FA page only renders when BeatStars actually challenges us. On the first real challenge, the worker writes a `sms-*.html` diagnostic — use it to tighten `SMS_CODE_INPUT_SELECTORS` / `SMS_SUBMIT_SELECTORS` in `services/platforms/beatstars.py`.
- **Redis-backed rate limiter** — current limiter is in-memory and per-process. Fine for the single-uvicorn-worker MVP; not safe for multi-worker or multi-instance prod. Swap for `slowapi + limits` with a Redis storage backend before scaling out.
- **More platforms** — SoundCloud connector is **built** (see "What works today"), pending an Artist Pro account + app credentials to go live. Still nothing for Spotify (via DistroKid), Audiomack (OAuth), Bandcamp (headless).
- **Real worker queue** — arq, RQ, or Celery. Today's `asyncio.create_task` loses in-flight uploads on every container restart (Render redeploys, scale events).
- **BeatStars progress reporting** — connector accepts a `progress_cb` per the new base.py signature but doesn't call it yet. Uppy emits progress events on `.uppy-StatusBar`; capture via `page.evaluate` and feed the callback (YouTube already does this, see `youtube.py::_do_upload`).
- **File storage on object store** — `services/storage.py` writes to disk under `STORAGE_DIR`. ⚠️ **Render free tier has NO persistent disk** — uploads written to `/app/storage` are lost on every restart/redeploy. Acceptable for the free-tier MVP since files stream straight to YouTube; the casualty is retry-from-disk (`POST /uploads/{id}/retry` reuses on-disk files — those won't exist after a restart). Swap for R2/S3 via boto3 / aioboto3 when scaling, or re-add a `disk:` block to `render.yaml` on a paid plan.
- **HttpOnly cookie sessions** — token is in `localStorage`, vulnerable to XSS exfiltration. Move to HttpOnly+Secure+SameSite cookies if/when we accept user-rendered HTML or third-party scripts.
- **Transactional email beyond verification/reset** — "your upload is live", weekly digest. Wired SMTP service is generic enough that it's just templating + the right trigger points.
- **Stripe / billing** — `User.plan` exists but is just a string with no enforcement.
- **OAuth provider verification (Google)** — required before non-test-users can use YouTube. 4–6 week process; the app is technically ready, just blocked on Google review.

### Done since the previous revision

These were on the list and are now resolved — keep an eye out so you don't re-add them.

- ~~**Multi-worker migration safety**~~ — implemented (`RUN_MIGRATIONS_ON_BOOT` flag + standalone `python -m app.migrate`), but **currently running migrations on boot** on free tier since Render free can't use `preDeployCommand`. Re-enable the pre-deploy path on a paid plan. See Pitfalls.
- ~~**Real progress reporting (YouTube)**~~ — `MediaUploadProgress.progress()` per chunk → `progress_cb` → `job.targets[provider].progress`, throttled to ≥5% deltas. BeatStars still pending (see Known gaps above).
- ~~**Email verification**~~ — full register → email → /verify-email → stamp `email_verified_at` flow, resend endpoint, dismissible dashboard banner. See "Auth / Email verification flow".
- ~~**Tests**~~ — 42 tests covering auth, password policy, security primitives, DB URL normalization, rate limiter behind a proxy, email verification. Run from `backend/`: `python -m pytest tests/`.
- ~~**Mobile UX pass**~~ — hamburger drawer (`components/mobile-nav.tsx`) with the same workspace nav, upload page tightening, PageHeader stacks on mobile.
- ~~**Reverse-proxy IP handling**~~ — Dockerfile runs uvicorn with `--proxy-headers --forwarded-allow-ips '*'`; rate limiter behavior covered by tests in `tests/test_rate_limit.py`. Note: this still requires the upstream proxy (Render/Cloudflare/etc.) to be in front; the test verifies the *limiter side* of the contract.
- ~~**Production deployment**~~ — **LIVE** at `beatuploader.app` (Vercel) + `api.beatuploader.app` (Render free) + Resend email + Cloudflare DNS. See the "Production (LIVE...)" section near the top for the full topology, the BeatStars free-tier blocker, and the two debug commits awaiting revert.

### Docker / deploy gotchas learned the hard way (2026-05-25 deploy session)

The first prod deploy took 5 build iterations. Don't re-introduce these:
- **Base image must be Python ≥3.11.** Code uses `from datetime import UTC` (3.11+) in 10 files. The Playwright `-jammy` image ships Python 3.10 → `ImportError`. We use **`mcr.microsoft.com/playwright/python:v1.49.0-noble`** (Ubuntu 24.04, Python 3.12). Don't drop to `-jammy`.
- **Playwright pinned to `>=1.49.0,<1.50.0`** in `pyproject.toml` to match the base image's bundled Chromium. Unpinned, pip grabbed 1.60 against 1.49 binaries (version-mismatch launch failures). Bump image tag + pin together.
- **Dockerfile copies `app/` BEFORE `pip install -e .`** — `pyproject.toml` declares `packages = ["app"]`, so the editable install needs the source present. The old deps-first layer-cache ordering broke the build.

## Reference: Google Cloud OAuth setup

Enable YouTube Data API v3. Configure OAuth consent screen with scopes:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`
- `openid` + `.../auth/userinfo.email` + `.../auth/userinfo.profile` (for the "Continue with Google" sign-in flow)

Create OAuth client → Web application → redirect URIs (one for sign-in, one for per-platform connect):
- `{BACKEND_BASE_URL}/api/auth/google/callback`
- `{BACKEND_BASE_URL}/api/platforms/youtube/callback`

Add your account as a test user while the app is in Testing mode. Set `YOUTUBE_CLIENT_ID` + `YOUTUBE_CLIENT_SECRET` in `backend/.env`, restart server.

Common pitfalls:
- `access_denied` → forgot to add the Google account as a test user
- `redirect_uri_mismatch` → URI in Google Console must match `{BACKEND_BASE_URL}/...` exactly (trailing slash counts)
- Token exchange `invalid_grant` → re-doing flow without `prompt=consent` won't issue a refresh_token; our `start_authorize` already forces this
