# Beatuploader

Multi-platform beat upload SaaS. Producers connect their accounts (BeatStars, YouTube, etc.) and push beats to every platform from one dashboard. Target users: independent producers selling beats.

## Layout

```
beatuploader/
├── frontend/   Vite + React 19 + TS + Tailwind v4 + motion + TanStack Query
└── backend/    FastAPI + async SQLAlchemy 2.0 + Pydantic v2 + Playwright (sync)
```

Frontend talks to backend via `/api/*` over JSON (multipart for uploads). Auth is JWT Bearer in `Authorization` header, token in `localStorage`.

## Run dev

```powershell
# Backend
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload          # http://localhost:8000  (docs at /docs)

# Frontend
cd frontend
npm run dev                            # http://localhost:5173
```

**First-time setup:**
- Backend venv: `python -m venv .venv && .venv\Scripts\python.exe -m pip install -e .`
- Playwright: `playwright install chromium` (~150MB)
- DB: created automatically on first boot via `init_db()` (`create_all`)

**Current dev setup runs on port 8001**, not 8000. There's no `backend/.env` — the user is running on **all dev defaults**. Backend launched with `BACKEND_BASE_URL=http://localhost:8001` env override; `frontend/.env.local` has `VITE_API_BASE=http://127.0.0.1:8001/api`. Why: Windows leaves zombie LISTENING entries on port 8000 after a hard kill that survive for many minutes; 8001 was a workaround. If 8000 is free, prefer it.

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

**Registry** is in `registry.py`. Currently wired: `youtube`, `beatstars`. Stubs raising `NotImplementedError`: `soundcloud`. Other providers in `PlatformProvider` enum (spotify, audiomack, bandcamp) aren't even stubbed yet — adding any of them just requires a file and registry entry.

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

### Auth (`backend/app/api/auth.py`, `frontend/src/lib/auth.tsx`)

Three sign-in surfaces, all issue the same Beatuploader JWT:

1. **Email + password**: `POST /api/auth/register`, `POST /api/auth/login`. Race on register caught (`IntegrityError` → 409).
2. **Google sign-in**: `POST /api/auth/google/start` returns a Google authorize URL with scopes `openid email profile youtube.upload youtube.readonly`. After approval → `GET /api/auth/google/callback` → verify ID token, match by `google_sub` then auto-link by email, create user if neither, **also upsert the YouTube `PlatformConnection`** from the same token exchange. Redirects to `${FRONTEND}/auth/google#token=<jwt>` (URL **fragment** — never hits server logs).
3. (Headless) BeatStars credentials: `POST /api/platforms/beatstars/credentials` with username/password. Validates by logging in via Playwright, captures cookies, encrypts + persists. Different from sign-in — doesn't issue a Beatuploader JWT.

**User model nuances:**
- `password_hash` is nullable (Google-only users don't have one). Login rejects when `password_hash is None`.
- `google_sub` is a nullable unique index.

**Settings:**
- `PATCH /api/auth/me` — change handle (email change is intentionally not supported)
- `POST /api/auth/change-password` — change password. Requires `current_password` unless user has none (Google-only setting one for the first time).
- `DELETE /api/auth/me` — delete account. Body `{confirm_handle}` must match. Cascades platforms/uploads/beats/files.

**Common code:**
- `deps.py::get_current_user` decodes JWT, catches `ValueError` (bad token) and `(TypeError, ValueError)` from `int(sub)` → 401
- Frontend `lib/auth.tsx` hydrates user via `GET /api/auth/me` on mount; `setUnauthorizedHandler` clears token on any 401 → kicks to `/login`
- Sign-in OAuth state JWT carries `purpose=signin` (no user_id); platform-connect state carries `uid`. Don't confuse them in callbacks.

### Per-platform OAuth (e.g. YouTube)

Distinct from sign-in. For YouTube:
1. Frontend `POST /api/platforms/youtube/connect` → returns `authorize_url` (signed state JWT embeds `user_id`)
2. Frontend redirects to Google
3. Google → `GET /api/platforms/youtube/callback?code=&state=` → verify state, exchange code, encrypt tokens via Fernet, upsert `PlatformConnection`, 302 to `${FRONTEND}/platforms?status=connected&provider=youtube`
4. Frontend reads URL params on mount, shows banner, refetches platforms

Redirect URI is computed from `BACKEND_BASE_URL` in `.env` — must match exactly what's registered in Google Console.

### BeatStars (headless, deep-dive)

The hardest integration and the product's differentiator. Lives in `services/platforms/beatstars.py`. **All selectors are verified against the live UI (May 2026).**

**Auth flow** (`_do_login`):
- Two-step: email page (`#oath-email`) → click Continue → password page (`#userPassword`) → click Continue
- BeatStars redirects unknown emails to `/sign-up` — we detect this and surface "No BeatStars account found"
- SMS 2FA: when BeatStars triggers it (new device, suspicious IP), we detect `/verify`-style URLs OR known body text patterns and raise. **Not yet automated** — user has to log into BeatStars in their normal browser once to clear the challenge, then retry from our side. Detection live; interactive resolution TODO.
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
├── id, email, handle, password_hash (nullable), google_sub (nullable, unique), plan, created_at
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
- **Platform tokens** — encrypted at rest with Fernet (`security.py::encrypt_token`). The Fernet instance reads `TOKEN_ENCRYPTION_KEY` directly — **no silent padding/derivation**. Pre-this-audit code derived keys from short strings, which is dangerous; that's been removed. `decrypt_token` wraps any failure in a clean `RuntimeError` so we don't leak crypto internals.
- **Secret validation** — `config.py::_validate_secrets` runs at startup. In `DEBUG=true` (default) it warns; in `DEBUG=false` (prod) it raises if `JWT_SECRET` is the dev default, `< 32` chars, or `TOKEN_ENCRYPTION_KEY` isn't a valid Fernet key.
- **Error responses** — never expose raw exception text to clients. All OAuth callback/save/retry paths log the full exception server-side via `log.exception(...)` and return a generic message.
- **File uploads** — extension allowlist + per-role size limit enforced in `services/storage.py::save_upload`. Streams to disk with a running byte count; aborts mid-stream and cleans up the partial file if over the limit.
- **JWT** — HS256, 7-day expiry. Subject claim is the user ID (int). State JWTs for OAuth are signed with the same secret but carry a `purpose` field to distinguish sign-in from platform-connect.
- **Token in URL fragment** (Google sign-in callback redirect) — fragments don't hit server logs (HTTP spec). Browser history is the only risk.
- **CORS** — `cors_origins` env var, comma-separated. Default localhost.
- **CSRF** — not applicable (Bearer JWT, not cookies).
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

- **No migrations** — `init_db()` does `create_all` on boot. Adding a column to an existing table is a no-op (Postgres/SQLite both); you have to drop the DB to apply. Wire Alembic before any breaking schema change in prod.
- **No real worker queue** — `asyncio.create_task` lives in the process. Process crash = in-flight uploads lost. The `_in_flight` set holds references but only prevents GC; doesn't survive a restart.
- **Token refresh isn't persisted** — Google's `Credentials` object auto-refreshes via the refresh_token, but the new access token isn't written back to the DB. After ~1h idle, next upload silently re-refreshes (fine) but DB holds stale access token. Add a refresh hook before production.
- **BeatStars selectors can break anytime** — Angular CSS classes (`_ngcontent-ng-c*`) change every BeatStars deploy. We pin to `data-qa`, `data-cy`, IDs, and visible text. If something stops working, capture a diagnostic and check the selectors.
- **Cropper / Uppy editor blocking** — both Uppy's built-in editor (`.uppy-DashboardContent-panel--editor`) and BeatStars's post-upload Cropper.js (`.cropper-modal`) intercept clicks. Always dismiss them before trying to click anything else. The artwork upload + license toggle paths both run `_close_cropper_if_open` defensively.
- **Material slide-toggle clicks** — `mat-slide-toggle` wraps a hidden `<input role="switch">`. Clicking the wrapper through Playwright's `.click()` doesn't reliably register with Angular's change detection. Use `page.evaluate` to call `.click()` on the input directly. See `_enable_license`.
- **Genre chips can be disabled at 3/3 limit** — BeatStars carries 3 genres over from the user's last upload. If we try to add a new genre, the input is `disabled="true"`. Our `_set_chip` no-ops silently in that case; the existing 3 stick. By design.
- **Diagnostics may leak** — `./storage/diagnostics/` contains BeatStars's logged-in DOM snapshots. `storage/` is gitignored, but don't share these casually.
- **Account-deletion JWT** — after `DELETE /api/auth/me`, the user's outstanding JWT is still cryptographically valid but `get_current_user` now 401s because the user row is gone. Frontend handles this via the 401 → logout flow.

## Known gaps / TODO

Ranked roughly by impact:

- **BeatStars SMS 2FA interactive flow** — detection is in place; resolution is not. When BeatStars challenges us with SMS, we surface "asked for SMS verification" and stop. A real interactive flow would prompt the user for the code via the UI and submit it. Most users get past this by logging in once in their normal browser to clear the device challenge.
- **More platforms** — SoundCloud (OAuth, easy), Spotify (via DistroKid), Audiomack (OAuth), Bandcamp (headless). All zero progress.
- **Production deployment** — Dockerfile, hosted Postgres, R2/S3 for file storage, Vercel for frontend, OAuth redirect URI updates in Google Console. Required for Google verification.
- **Token refresh persistence** — see above
- **Real worker queue** — arq, RQ, or Celery
- **Real progress reporting** — YouTube resumable upload has per-chunk callbacks. Wire them through to `job.targets[provider].progress`. BeatStars's Uppy emits progress events too — could capture via page eval.
- **Alembic migrations** — required before any prod schema change
- **Email** (transactional) — verification, password reset, "your upload is live"
- **Stripe / billing** — `User.plan` exists but is just a string
- **Tests** — pytest+pytest-asyncio installed; zero tests written. Start with auth happy path + upload pipeline.
- **OAuth provider verification (Google)** — required before non-test-users can use YouTube. 4–6 week process.
- **Mobile UX pass** — desktop-first; sidebar hides at `md:` but upload page is cramped on phones

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
