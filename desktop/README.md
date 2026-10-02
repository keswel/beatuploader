# Beatuploader desktop

Tauri v2 shell around the existing app. Nothing is hosted: the FastAPI backend
runs on the user's machine as a sidecar, serves the React UI on
`127.0.0.1:<random port>`, and keeps everything in `%APPDATA%\Beatuploader`
(SQLite DB, uploaded files, logs). The key that encrypts platform tokens lives
in Windows Credential Manager (`Beatuploader / token-encryption-key`).

```
beatuploader.exe (this crate)          tray icon, window, auto-updater
 └─ backend/beatuploader-backend.exe   PyInstaller build of backend/app/desktop.py
     └─ serves frontend/dist-desktop   `vite build --mode desktop`
```

## Dev

```powershell
cd frontend; npm run build:desktop      # the backend serves this build
cd ..\desktop; npm install; npm run dev  # spawns backend\.venv python -m app.desktop
```

Debug builds run the backend from the repo venv with a visible console. Set
`YOUTUBE_CLIENT_ID`/`YOUTUBE_CLIENT_SECRET` in your shell to test YouTube.

## Release build (local)

```powershell
cd frontend; npm run build:desktop
cd ..\backend; .venv\Scripts\pyinstaller desktop.spec --noconfirm
cd ..\desktop
$env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -Raw ~\.tauri\beatuploader-updater.key
$env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = ""
$env:CARGO_BUILD_JOBS = 4   # parallel rustc on Windows can hit STATUS_DLL_INIT_FAILED
npm run build
# → src-tauri\target\release\bundle\nsis\Beatuploader_<ver>_x64-setup.exe (+ .sig)
```

## Shipping an update

1. Bump `version` in `src-tauri/tauri.conf.json` (and `Cargo.toml`, `package.json`).
2. `git tag v<version> && git push origin v<version>`.
3. `.github/workflows/desktop-release.yml` builds, signs, and publishes the
   release + `latest.json`. Installed apps pick it up on next launch (or tray →
   "Check for updates").

The updater **public** key is in `tauri.conf.json`. The **private** key is
`~/.tauri/beatuploader-updater.key` — back it up and put it in the repo
secret `TAURI_SIGNING_PRIVATE_KEY`. Lose it and existing installs can never
auto-update again (they'd need a manual reinstall).

## YouTube OAuth

Needs a Google OAuth client of type **Desktop app** (not the hosted "Web
application" client). Desktop clients accept any `http://127.0.0.1:<port>`
loopback redirect, so the random port is fine. The consent page opens in the
system browser (Google blocks OAuth inside embedded webviews); the callback
lands on the local backend and the app polls until the connection appears.

## Security model (local)

- The backend binds 127.0.0.1 only, rejects any `Host` other than its own
  loopback origin (DNS-rebinding), and requires the per-launch session token
  (`X-Beatuploader-Session`) on every `/api` call except OAuth callbacks.
- The token reaches only the app's own page (injected into `index.html`).
  The served UI gets **no** Tauri IPC — only the bundled splash page does.
- The backend exits when the shell's stdin pipe closes, so killing or
  crashing the shell never leaves an orphan holding file locks (which would
  break the updater).
