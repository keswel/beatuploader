//! Beatuploader desktop shell.
//!
//! The whole app is the existing FastAPI backend + React UI, run locally:
//!   1. pick a free loopback port + a per-launch session secret
//!   2. spawn the backend sidecar (`backend/beatuploader-backend.exe` from the
//!      bundle; `python -m app.desktop` in debug builds) with them
//!   3. show the bundled splash until /health answers, then point the window
//!      at http://127.0.0.1:<port> — the backend serves the UI there
//!   4. live in the tray (closing the window hides it), check for updates
//!
//! The backend exits on its own when our stdin pipe closes, so it can't
//! outlive the shell even if we crash.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use rand::distributions::{Alphanumeric, DistString};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WindowEvent};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;

const BACKEND_READY_TIMEOUT: Duration = Duration::from_secs(60);

#[derive(Default)]
struct Backend(Mutex<Option<Child>>);

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind("127.0.0.1:0")?.local_addr()?.port())
}

fn backend_command(app: &AppHandle) -> Result<Command, String> {
    if cfg!(debug_assertions) {
        // `tauri dev`: run the backend straight from the repo's venv.
        let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend");
        let mut cmd = Command::new(backend_dir.join(".venv/Scripts/python.exe"));
        cmd.args(["-m", "app.desktop"]).current_dir(&backend_dir);
        return Ok(cmd);
    }
    let exe = app
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?
        .join("backend")
        .join("beatuploader-backend.exe");
    if !exe.exists() {
        return Err(format!("Backend not found at {}", exe.display()));
    }
    Ok(Command::new(exe))
}

fn spawn_backend(app: &AppHandle, port: u16, session: &str) -> Result<Child, String> {
    let mut cmd = backend_command(app)?;
    cmd.env("BEATUPLOADER_PORT", port.to_string())
        .env("BEATUPLOADER_SESSION", session)
        // Held open for the child's lifetime; EOF = shell is gone, exit.
        .stdin(Stdio::piped());

    // Google "Desktop app" OAuth client, baked in at build time (see
    // desktop/README.md). For desktop clients Google doesn't treat the
    // secret as confidential. In dev, the backend reads them from the env.
    if let Some(id) = option_env!("BEATUPLOADER_YOUTUBE_CLIENT_ID") {
        cmd.env("YOUTUBE_CLIENT_ID", id);
    }
    if let Some(secret) = option_env!("BEATUPLOADER_YOUTUBE_CLIENT_SECRET") {
        cmd.env("YOUTUBE_CLIENT_SECRET", secret);
    }

    if !cfg!(debug_assertions) {
        // Backend logs to %APPDATA%\Beatuploader\logs; no console window.
        cmd.stdout(Stdio::null()).stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
    }
    cmd.spawn().map_err(|e| format!("Couldn't start the backend: {e}"))
}

/// Poll GET /health until it returns 200. Raw HTTP over TcpStream so we don't
/// pull in an HTTP client crate for one request.
fn wait_until_ready(app: &AppHandle, port: u16) -> Result<(), String> {
    let deadline = Instant::now() + BACKEND_READY_TIMEOUT;
    while Instant::now() < deadline {
        if let Some(child) = app.state::<Backend>().0.lock().unwrap().as_mut() {
            if let Ok(Some(status)) = child.try_wait() {
                return Err(format!("The backend exited during startup ({status})."));
            }
        }
        if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", port)) {
            let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
            let req = format!(
                "GET /health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
            );
            let mut buf = [0u8; 16];
            if stream.write_all(req.as_bytes()).is_ok()
                && stream.read(&mut buf).is_ok()
                && buf.starts_with(b"HTTP/1.1 200")
            {
                return Ok(());
            }
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    Err("The backend didn't start within a minute.".into())
}

fn stop_backend(app: &AppHandle) {
    if let Some(mut child) = app.state::<Backend>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn show_startup_error(app: &AppHandle, message: &str) {
    log::error!("{message}");
    if let Some(window) = app.get_webview_window("main") {
        let js = format!(
            "window.showError({})",
            serde_json::Value::from(format!("{message} Restart Beatuploader to try again."))
        );
        let _ = window.eval(&js);
    }
}

fn start_backend(app: AppHandle) {
    std::thread::spawn(move || {
        let port = match free_port() {
            Ok(p) => p,
            Err(e) => return show_startup_error(&app, &format!("No free local port: {e}.")),
        };
        let session = Alphanumeric.sample_string(&mut rand::thread_rng(), 48);
        match spawn_backend(&app, port, &session) {
            Ok(child) => *app.state::<Backend>().0.lock().unwrap() = Some(child),
            Err(e) => return show_startup_error(&app, &e),
        }
        if let Err(e) = wait_until_ready(&app, port) {
            stop_backend(&app);
            return show_startup_error(&app, &e);
        }
        let url = Url::parse(&format!("http://127.0.0.1:{port}/dashboard")).unwrap();
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.navigate(url);
        }
        if !cfg!(debug_assertions) {
            tauri::async_runtime::spawn(check_for_updates(app.clone(), false));
        }
    });
}

async fn check_for_updates(app: AppHandle, user_initiated: bool) {
    let result = match app.updater() {
        Ok(updater) => updater.check().await,
        Err(e) => Err(e),
    };
    match result {
        Ok(Some(update)) => {
            let prompt = format!(
                "Beatuploader {} is available (you have {}).\n\nInstall it now? The app will restart.",
                update.version, update.current_version
            );
            let handle = app.clone();
            app.dialog()
                .message(prompt)
                .title("Update available")
                .buttons(MessageDialogButtons::OkCancelCustom(
                    "Install".into(),
                    "Later".into(),
                ))
                .show(move |install| {
                    if install {
                        tauri::async_runtime::spawn(async move {
                            // The installer replaces backend files — release
                            // the running sidecar's locks first.
                            stop_backend(&handle);
                            if let Err(e) = update.download_and_install(|_, _| {}, || {}).await {
                                log::error!("update failed: {e}");
                                handle
                                    .dialog()
                                    .message(format!("The update failed: {e}"))
                                    .kind(MessageDialogKind::Error)
                                    .blocking_show();
                            }
                            handle.restart();
                        });
                    }
                });
        }
        Ok(None) if user_initiated => {
            app.dialog()
                .message("You're on the latest version.")
                .title("No updates")
                .show(|_| {});
        }
        Ok(None) => {}
        Err(e) => {
            log::warn!("update check failed: {e}");
            if user_initiated {
                app.dialog()
                    .message(format!("Couldn't check for updates: {e}"))
                    .kind(MessageDialogKind::Error)
                    .show(|_| {});
            }
        }
    }
}

fn build_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Open Beatuploader", true, None::<&str>)?;
    let update = MenuItem::with_id(app, "update", "Check for updates", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &update, &quit])?;

    TrayIconBuilder::with_id("main")
        .icon(app.default_window_icon().unwrap().clone())
        .tooltip("Beatuploader")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => show_main_window(app),
            "update" => {
                tauri::async_runtime::spawn(check_for_updates(app.clone(), true));
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        // Must be first: a second launch just focuses the running instance.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_main_window(app);
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Backend::default())
        .setup(|app| {
            build_tray(app.handle())?;
            start_backend(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing the window keeps Beatuploader running in the tray, so
            // uploads in flight finish (and, later, export-watching keeps going).
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Beatuploader")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                stop_backend(app);
            }
        });
}
