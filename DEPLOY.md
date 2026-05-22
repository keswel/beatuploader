# Deployment runbook

Hosting target: **Render** (backend + Postgres + persistent disk) + **Vercel** (frontend) + **Resend** (transactional email).

End-to-end time from a clean GitHub fork to a working production site: ~30 minutes if you have a domain ready, ~60 minutes if you're buying one mid-flight.

> Anything that mentions a domain assumes `beatuploader.com`. Substitute your own. Backend lives at `api.<domain>`, frontend at `<domain>`.

---

## Prerequisites

You'll need accounts on:

| Service     | Why                                          | Free tier?                  |
|-------------|----------------------------------------------|-----------------------------|
| GitHub      | Source of truth that Render + Vercel deploy from | Yes                       |
| Render      | Backend container + Postgres + disk          | Free tier OK for trial; bump Postgres to Starter ($7/mo) before launch |
| Vercel      | Frontend hosting                              | Yes (Hobby)                 |
| Resend      | Transactional email for password reset       | 3,000 emails/mo on free tier |
| Cloudflare  | DNS (or whoever manages your domain)         | Yes                         |
| Google Cloud | OAuth credentials (YouTube + sign-in)        | Yes                         |
| Sentry (optional) | Error tracking                          | 5k errors/mo free           |

A domain. Cloudflare Registrar is the easiest if you don't already have one.

---

## 1. Generate secrets

Both of these must be different per environment. **Never re-use dev secrets in prod.**

```powershell
# In backend/ with the venv active:
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('TOKEN_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Save the output — you'll paste it into Render in step 4.

If you lose `TOKEN_ENCRYPTION_KEY` after going live, every encrypted token in the DB (BeatStars passwords, YouTube refresh tokens, BeatStars cookies) becomes unrecoverable and users will need to reconnect every platform.

---

## 2. Set up Google Cloud OAuth (production)

You said you already have prod creds — skim this to confirm the redirect URIs match.

1. **OAuth consent screen** → Edit:
   - App name, support email, etc. — these show on the consent screen.
   - Authorized domains: add `<yourdomain>`.
   - Scopes: `openid`, `userinfo.email`, `userinfo.profile`, `youtube.upload`, `youtube.readonly`.
2. **Credentials** → your OAuth 2.0 Client ID → Edit:
   - Authorized redirect URIs (add both):
     - `https://api.<yourdomain>/api/auth/google/callback`
     - `https://api.<yourdomain>/api/platforms/youtube/callback`
3. While the app is still in **Testing** mode, add yourself + each test user under "Test users". You'll need to publish + go through Google verification before opening to the public — that takes 4–6 weeks. See [CLAUDE.md → OAuth provider verification](./CLAUDE.md#known-gaps--todo).

---

## 3. Set up Resend (or any SMTP provider)

The app speaks SMTP, so anything with an SMTP relay works. Resend is the simplest.

1. Sign up at https://resend.com.
2. **Domains** → Add `<yourdomain>` → add the DNS records to your DNS provider (SPF, DKIM, return-path). Wait for "Verified" — usually < 5 min on Cloudflare.
3. **API Keys** → Create. Copy the `re_...` key.

The SMTP values you'll set on Render in step 4:

| Variable        | Value                                      |
|-----------------|--------------------------------------------|
| `SMTP_HOST`     | `smtp.resend.com`                          |
| `SMTP_PORT`     | `587`                                      |
| `SMTP_USER`     | `resend`                                   |
| `SMTP_PASSWORD` | `re_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`          |
| `SMTP_FROM`     | `Beatuploader <noreply@<yourdomain>>`      |

The `noreply@` mailbox must be on the verified Resend domain — they reject mismatches.

---

## 4. Deploy backend to Render

1. Push this repo to GitHub if you haven't.
2. Render → **New** → **Blueprint** → connect your GitHub account → pick the repo. Render reads [`render.yaml`](./render.yaml) and shows what it'll create:
   - `beatuploader-db` (Postgres)
   - `beatuploader-api` (Docker web service + 10 GB disk)
3. Render prompts for the secrets marked `sync: false` in `render.yaml`. Paste:
   - `TOKEN_ENCRYPTION_KEY` — from step 1
   - `BACKEND_BASE_URL` — `https://api.<yourdomain>` (use the temporary `.onrender.com` URL for the first boot, swap to the custom domain after step 6)
   - `FRONTEND_BASE_URL` — `https://<yourdomain>`
   - `CORS_ORIGINS` — `https://<yourdomain>` (comma-separate if you want to keep dev origins working)
   - `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` — from step 2
   - `SMTP_*` — from step 3
   - `SENTRY_DSN` — if you're using Sentry (otherwise leave blank)
4. Apply. Render builds the Docker image (~3–4 min for the Playwright base layer the first time, faster after that), runs migrations, and starts the web service.
5. While it builds, verify `/health` and `/health/ready` work once it's up:
   ```powershell
   curl https://beatuploader-api.onrender.com/health
   curl https://beatuploader-api.onrender.com/health/ready
   ```
   `health/ready` failing means migrations didn't run — check the deploy logs.

---

## 5. Deploy frontend to Vercel

1. Vercel → **Add New** → **Project** → pick the same GitHub repo.
2. Configure:
   - **Root directory**: `frontend`
   - **Framework preset**: Vite (auto-detected via `vercel.json`)
   - **Environment Variables**:
     - `VITE_API_BASE` = `https://api.<yourdomain>/api`
3. Deploy. Vercel runs `npm run build` (which includes `tsc -b`); ~1 min.
4. Once it's up, you should see the landing page at `<project>.vercel.app`.

---

## 6. Wire up custom domain

DNS at Cloudflare (or wherever):

| Record  | Name | Target                                |
|---------|------|---------------------------------------|
| `CNAME` | `@`  | `cname.vercel-dns.com` (Vercel apex)  |
| `CNAME` | `www` | `cname.vercel-dns.com`               |
| `CNAME` | `api` | `<your render service>.onrender.com` |

In Cloudflare set the `api` proxy status to **DNS only** (grey cloud) for the first issuance — Render needs to see the real origin to validate the TLS cert. You can flip it to proxied later if you want WAF/caching.

In Vercel → Project → Domains: add `<yourdomain>` and `www.<yourdomain>`.
In Render → Service → Settings → Custom Domains: add `api.<yourdomain>`.

Wait for both to show "Verified" (~5 min).

---

## 7. Final wiring

Now that the real URLs exist, update three things:

1. **Render** env vars (Settings → Environment) — flip placeholder `*.onrender.com` URLs to the real `api.<yourdomain>` and frontend `<yourdomain>`. Redeploy.
2. **Google Cloud Console** → OAuth client → if you used placeholder redirect URIs earlier, replace them with the real `api.<yourdomain>` ones now.
3. **Vercel** — if you used the temporary backend URL in `VITE_API_BASE`, switch it to `https://api.<yourdomain>/api` and trigger a redeploy.

---

## 8. Smoke test

In an incognito window, hit `https://<yourdomain>`:

- [ ] Landing page renders.
- [ ] Click "Sign in" → register a new account with email + password. You should land on the dashboard.
- [ ] Log out, then "Forgot password" → check the email actually arrives.
- [ ] Re-sign-in via "Continue with Google" — should work and auto-connect YouTube.
- [ ] Platforms page → connect BeatStars with real creds.
- [ ] Upload a beat with at least an MP3 → wait for it to finish on both targets.

If any step fails:
- Check Render logs (`Logs` tab) for the backend.
- Check the Vercel deployment logs for the frontend.
- The backend writes Playwright diagnostics to `/app/storage/diagnostics/` on the persistent disk — connect to the Render shell to grab them: `Shell` tab → `ls /app/storage/diagnostics/`.

---

## Going forward

Most config changes can stay in `render.yaml` for blueprint-tracked values + the Render dashboard for `sync: false` secrets. Pushing to `main` triggers an auto-deploy of both services.

When you outgrow the current setup (probably in this order):
1. **Add a Redis-backed rate limiter.** In-memory limiter only works for one process.
2. **Move file storage from disk to R2/S3.** Persistent disks don't scale across instances.
3. **Replace asyncio.create_task with arq + Redis.** In-flight uploads die with the container on every redeploy.

Migrations already run as a Render `preDeployCommand` against the new image before traffic shifts — see `render.yaml`. Multi-worker scaling won't race the alembic lock.

See [CLAUDE.md → Known gaps](./CLAUDE.md#known-gaps--todo) for the full list.
