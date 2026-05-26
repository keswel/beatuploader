"""BeatStars connector via headless browser automation.

BeatStars has no public API. We drive their web UI with Playwright.

Selectors verified against the BeatStars Angular app (May 2026 layout).
Stable picks: `data-qa`, `data-cy`, and IDs. AVOID `_ngcontent-ng-c*` attrs and
generated CSS classes — they change on every BeatStars deploy.

Flow:
1. Credentials → /login → capture storage_state (cookies + localStorage)
2. Upload navigates to studio.beatstars.com (different subdomain — cookies must
   be scoped to .beatstars.com or set in storage_state for the subdomain too)
3. Uppy file picker opens automatically via ?create=true; we set_input_files on
   the hidden <input type="file">, wait for the title input to become usable,
   then fill the form and publish.

Uses **sync Playwright + asyncio.to_thread** because uvicorn on Windows uses
the Selector event loop policy which doesn't support subprocesses.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from app.models.platform import PlatformConnection, PlatformProvider
from app.security import decrypt_token, encrypt_token
from app.services.platforms._browser import (
    browser_session,
    deserialize_storage_state,
    serialize_storage_state,
)
from app.services.platforms.base import (
    AuthMethod,
    BeatMetadata,
    OAuthRedirect,
    PlatformConnector,
    ProgressCallback,
    UploadHandle,
    UploadProgress,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# URLs
# ─────────────────────────────────────────────────────────────────────────────

LOGIN_URL = "https://www.beatstars.com/login"
UPLOAD_URL = "https://studio.beatstars.com/content/tracks/uploaded?create=true"
LOGGED_IN_HOST = "studio.beatstars.com"  # login redirects here

# ─────────────────────────────────────────────────────────────────────────────
# Selectors (verified from BeatStars HTML, May 2026)
# ─────────────────────────────────────────────────────────────────────────────

# Login page
SEL_EMAIL = "#oath-email"
SEL_PASSWORD = "#userPassword"
SEL_LOGIN_SUBMIT = 'button[type="submit"]:has-text("Continue")'
SEL_LOGIN_ERROR = '[role="alert"], .error, .form-error, .bs-error'

# Upload modal (Uppy)
SEL_UPPY_FILE_INPUT = 'input.uppy-Dashboard-input[type="file"]:not([webkitdirectory])'

# First-time onboarding carousel (5 slides) — shows once per BeatStars session.
# Wrapped in bs-responsive-dialog-feature-template; specific enough to disambiguate
# from BeatStars's other dialogs (player, chargebee, share dialog, etc.).
# Note: the modal renders AFTER initial Angular hydration, so we need a long
# wait window when looking for it.
SEL_ONBOARDING_CLOSE = 'bs-responsive-dialog-feature-template .close-btn-wrapper button'

# Main form fields
SEL_FORM_TITLE = "#title"
SEL_FORM_KEY = 'bs-select[data-qa="select_key"] select'
SEL_FORM_BPM = 'bs-text-input[data-qa="input_bpm"] input[type="number"]'
SEL_FORM_TAGS_INPUT = 'bs-chips-input[data-qa="input_tag"] input'
SEL_FORM_GENRE_INPUT = 'bs-chips-key-value[data-qa="input_genre"] input'

# Publishing options
SEL_TRACK_TYPE = '#trackType select'
SEL_VISIBILITY = '#trackVisibility select'

# Artwork upload — Angular component with its own Uppy instance.
# `studiosmartimageupload` directive on bs-upload-files-dialog inside the artwork wrapper.
SEL_ARTWORK_WRAPPER = "studio-track-form-artwork-upload"
SEL_ARTWORK_EDIT_BTN = 'button[data-cy="artwork-drop-down-button-button"]'

# License cards — each is a .license-card identified by its label text.
# A card has class `prevent-enabling` while the required files haven't been uploaded.
SEL_LICENSE_CARD = ".license-card"
SEL_LICENSE_PRICE_INPUT = 'input[data-cy="contract_price"]'

# Map our license_type enum to the label text inside the card.
LICENSE_LABEL = {
    "EXCLUSIVE": "Exclusive License",
    "PREMIUM_PLUS": "Premium Plus License",
    "PREMIUM": "Premium License",
    "UNLIMITED": "Unlimited License",
}

# Publish
SEL_PUBLISH_BUTTON = 'button[data-cy="publish_btn-button"]'

# Success — share dialog appears after publish
SEL_SUCCESS_DIALOG = 'mat-dialog-container:has-text("Share your CONTENT")'
SEL_SUCCESS_MARKETPLACE_LINK = 'bs-text-input:has(label:has-text("Marketplace Link")) input'

# Timing
TIMEOUT_NAV = 30_000
TIMEOUT_ELEMENT = 15_000
TIMEOUT_UPLOAD = 180_000  # large WAVs can take a while

# ─────────────────────────────────────────────────────────────────────────────
# Form-data mapping helpers
# ─────────────────────────────────────────────────────────────────────────────

def normalize_key(raw: str | None) -> str | None:
    """Map free-text key like 'C# min', 'Bbm', 'F#M' to BeatStars enum like 'C_SHARP_MINOR'.

    Returns None if the key can't be parsed — caller should skip the field.
    """
    if not raw:
        return None
    s = raw.replace("♭", "b").replace("♯", "#").strip()
    m = re.match(r"^([A-Ga-g])\s*([b#])?\s*(.*)$", s)
    if not m:
        return None
    note = m.group(1).upper()
    accidental = m.group(2) or ""
    rest = m.group(3).lower().strip()

    # 'min', 'minor', 'm' (but not 'maj') → minor
    if "min" in rest or (rest.startswith("m") and not rest.startswith("ma")):
        quality = "MINOR"
    else:
        quality = "MAJOR"

    note_part = note
    if accidental == "#":
        note_part += "_SHARP"
    elif accidental == "b":
        note_part += "_FLAT"

    candidate = f"{note_part}_{quality}"
    # BeatStars doesn't expose every combo (no C♭m, F♭, F♭M, G♭m, B♯). Bail if invalid.
    valid = {
        "A_FLAT_MINOR", "A_FLAT_MAJOR", "A_MINOR", "A_MAJOR", "A_SHARP_MINOR", "A_SHARP_MAJOR",
        "B_FLAT_MINOR", "B_FLAT_MAJOR", "B_MINOR", "B_MAJOR",
        "C_FLAT_MAJOR", "C_MINOR", "C_MAJOR", "C_SHARP_MINOR", "C_SHARP_MAJOR",
        "D_FLAT_MINOR", "D_FLAT_MAJOR", "D_MINOR", "D_MAJOR", "D_SHARP_MINOR", "D_SHARP_MAJOR",
        "E_FLAT_MINOR", "E_FLAT_MAJOR", "E_MINOR", "E_MAJOR",
        "F_MINOR", "F_MAJOR", "F_SHARP_MINOR", "F_SHARP_MAJOR",
        "G_FLAT_MAJOR", "G_MINOR", "G_MAJOR", "G_SHARP_MINOR", "G_SHARP_MAJOR",
    }
    return candidate if candidate in valid else None


def clamp_tags(tags: list[str]) -> list[str]:
    """BeatStars allows max 3 tags, each min 2 / max 25 chars."""
    cleaned = [t.strip() for t in tags if t and 2 <= len(t.strip()) <= 25]
    return cleaned[:3]


def pick_licenses(
    license_type: str | None,
    *,
    has_master_wav: bool,
    has_tagged: bool,
    has_stems: bool,
) -> list[str]:
    """Decide which licenses to enable, per BeatStars's file requirements
    (verified against the live UI):

      MP3 only          → Basic (auto-on by BeatStars; we add nothing)
      MP3 + WAV         → PREMIUM, UNLIMITED
      MP3 + WAV + stems → PREMIUM, UNLIMITED, EXCLUSIVE

    PREMIUM_PLUS is not in the auto set; if a user wants it they pick it
    explicitly from the dropdown. We require MP3 + WAV for it.

    Specific license name → enable just that one, but only if its requirements
    are met. Returns [] if requirements aren't satisfied (caller can skip
    license-flipping; the listing still publishes with whatever Basic gives).
    """
    if license_type and license_type != "AUTO":
        if license_type not in LICENSE_LABEL:
            return []
        # Per-license feasibility check
        if not has_tagged:
            return []  # MP3 is needed for any license
        if license_type == "EXCLUSIVE" and not (has_master_wav and has_stems):
            return []
        if license_type in ("PREMIUM", "UNLIMITED", "PREMIUM_PLUS") and not has_master_wav:
            return []
        return [license_type]

    # AUTO
    chosen: list[str] = []
    if has_tagged and has_master_wav:
        chosen.append("PREMIUM")
        chosen.append("UNLIMITED")
        if has_stems:
            chosen.append("EXCLUSIVE")
    return chosen


# Back-compat alias in case anything still imports the old name
pick_license = pick_licenses


# ─────────────────────────────────────────────────────────────────────────────
# Login + outcome detection
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class LoginResult:
    storage_state: dict
    account_label: str | None


SMS_URL_HINTS = ("/verify-", "/challenge", "/2fa", "/sms", "/code", "verification")
SMS_TEXT_HINTS = (
    "verification code",
    "we sent",
    "we've sent",
    "enter the code",
    "enter code",
    "sms",
    "text message",
    "phone number ending",
    "6-digit",
    "6 digit",
)


# SMS-code form selectors. BeatStars's exact markup isn't pinned (their 2FA UI
# only appears when their fraud system challenges us), so we try a few common
# patterns. If a real challenge doesn't resolve, capture the diagnostic HTML and
# tighten these to match.
SMS_CODE_INPUT_SELECTORS = (
    'input[autocomplete="one-time-code"]',
    'input[name="code"]',
    'input[name="verification_code"]',
    'input[name="otp"]',
    'input[name="verificationCode"]',
    "#code",
    "#verification_code",
    "#otp",
    'input.code-input',
    'input[type="text"][maxlength="6"]',
    'input[type="tel"][maxlength="6"]',
)
SMS_SUBMIT_SELECTORS = (
    'button[type="submit"]:has-text("Verify")',
    'button[type="submit"]:has-text("Continue")',
    'button[type="submit"]:has-text("Submit")',
    'button[type="submit"]:has-text("Confirm")',
    'button:has-text("Verify")',
    'button:has-text("Continue")',
    'button[type="submit"]',
)


@dataclass
class SmsHandler:
    """Callbacks the API layer hands to _do_login so it can pause for a code."""

    on_detected: Callable[[str | None], None]  # called once when SMS is detected
    get_code: Callable[[], str | None]  # blocks; returns None to cancel


class SmsCancelled(RuntimeError):
    """Raised when the user cancels (or times out) the SMS challenge."""


def _detect_login_outcome(page: Page) -> str:
    """Return 'success' | 'bad_credentials' | 'sms' | 'captcha' | 'unknown'.

    Success criteria: redirected away from the oauth/login/sign-up subdomain to
    any other beatstars.com page. BeatStars sends you to www.beatstars.com/
    (homepage) after OAuth completes — that counts as success.
    """
    url = (page.url or "").lower()
    on_auth_page = (
        "oauth.beatstars.com" in url
        or "/login" in url
        or "/sign-up" in url
        or "/sign-in" in url
    )
    if "beatstars.com" in url and not on_auth_page:
        return "success"

    # SMS / 2FA detection — check URL first, then page text
    if any(h in url for h in SMS_URL_HINTS):
        return "sms"
    try:
        body_text = (page.inner_text("body") or "").lower()
    except Exception:
        body_text = ""
    if any(h in body_text for h in SMS_TEXT_HINTS):
        return "sms"

    err = page.query_selector(SEL_LOGIN_ERROR)
    if err is not None:
        text = (err.inner_text() or "").strip().lower()
        if "captcha" in text or "robot" in text or "are you human" in text:
            return "captcha"
        # Real bad-creds errors are usually short ("Invalid email or password")
        # — long alert texts are usually notifications/cookie banners.
        if text and len(text) < 200:
            return "bad_credentials"

    return "unknown"


def _capture_diagnostic(page: Page, *, label: str) -> str:
    """Dump url+title+screenshot to ./storage/diagnostics/. Returns a short tag for logs."""
    from datetime import datetime
    from pathlib import Path as _P

    try:
        out_dir = _P("./storage/diagnostics")
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        screenshot = out_dir / f"{label}-{ts}.png"
        html_dump = out_dir / f"{label}-{ts}.html"
        page.screenshot(path=str(screenshot), full_page=True)
        html_dump.write_text(page.content(), encoding="utf-8")
        title = (page.title() or "").strip()[:80]
        return f"url={page.url!r} title={title!r} screenshot={screenshot.name}"
    except Exception as exc:
        return f"failed to capture: {exc}"


def _read_account_label(page: Page) -> str | None:
    """Best-effort read of the logged-in user's handle."""
    for sel in [
        '[data-cy="user-menu"]',
        '[data-qa="user-menu"]',
        '.user-handle',
        'studio-header [class*="username"]',
    ]:
        try:
            el = page.query_selector(sel)
            if el is not None:
                txt = (el.inner_text() or "").strip()
                if txt:
                    return txt[:64]
        except Exception:
            continue
    return None


def _submit_sms_code(page: Page, code: str) -> None:
    """Type the SMS code into BeatStars's verification form and submit.

    Tries a single-input pattern first (the most common form), falling back to
    a 6-cell digit-per-input pattern. Raises RuntimeError if neither matches —
    the caller should treat that as "selectors out of date, capture a diagnostic".
    """
    code = code.strip()
    filled = False

    for sel in SMS_CODE_INPUT_SELECTORS:
        try:
            el = page.query_selector(sel)
            if el is None:
                continue
            if not el.is_visible():
                continue
            el.fill(code)
            filled = True
            break
        except Exception:  # noqa: BLE001
            continue

    if not filled:
        # Try the digit-per-input pattern. BeatStars might use 6 inputs that
        # auto-advance on input.
        try:
            inputs = page.query_selector_all('input[maxlength="1"]')
            visible = [i for i in inputs if i.is_visible()]
            if len(visible) >= 6 and len(code) == 6:
                for i, ch in zip(visible[:6], code):
                    i.fill(ch)
                filled = True
        except Exception:  # noqa: BLE001
            pass

    if not filled:
        raise RuntimeError(
            "Couldn't locate the BeatStars SMS code input field. "
            "Selectors may need updating — check ./storage/diagnostics/sms-*.html."
        )

    # Submit. Some forms auto-submit on the 6th digit; we still click in case.
    for sel in SMS_SUBMIT_SELECTORS:
        try:
            btn = page.query_selector(sel)
            if btn is None:
                continue
            if not btn.is_visible() or not btn.is_enabled():
                continue
            btn.click()
            break
        except Exception:  # noqa: BLE001
            continue

    # Wait for either a redirect off the auth subdomain or a re-render of the
    # form (e.g. with an error). Best-effort: ignore timeouts and let the
    # outcome detector make the call.
    try:
        page.wait_for_load_state("networkidle", timeout=TIMEOUT_NAV)
    except PlaywrightTimeoutError:
        pass


def _read_sms_hint(page: Page) -> str | None:
    """Pull a short user-friendly hint from the SMS page (e.g. masked phone number)."""
    try:
        body = (page.inner_text("body") or "").strip()
    except Exception:  # noqa: BLE001
        return None
    # Look for the line that mentions "code" — usually contains the phone hint
    for line in body.splitlines():
        line = line.strip()
        if not line or len(line) > 200:
            continue
        lower = line.lower()
        if any(h in lower for h in ("code", "verification", "we sent", "we've sent")):
            return line
    return None


def _do_login(
    username: str,
    password: str,
    *,
    sms_handler: SmsHandler | None = None,
) -> LoginResult:
    """Sync — meant to be wrapped in asyncio.to_thread.

    BeatStars uses a two-step OAuth-style login:
      1. Page 1: email input + Continue button
      2. Page 2: password input + Continue button

    If BeatStars challenges us with SMS 2FA and ``sms_handler`` is provided, we
    call ``on_detected`` (giving the API endpoint a chance to return a
    challenge_id to the user) and block on ``get_code`` until the user
    submits the code. With no handler we raise immediately.
    """
    with browser_session() as (_, context):
        page = context.new_page()
        try:
            # BeatStars is an Angular SPA — wait for client-side render
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=TIMEOUT_NAV)

            # Step 1: email
            page.wait_for_selector(SEL_EMAIL, timeout=TIMEOUT_ELEMENT * 2, state="visible")
            page.fill(SEL_EMAIL, username)
            page.click(SEL_LOGIN_SUBMIT, timeout=TIMEOUT_ELEMENT)

            # Step 2: password — appears on the same domain after the email step.
            # If the email doesn't exist, BeatStars redirects to /sign-up.
            try:
                page.wait_for_selector(
                    SEL_PASSWORD, timeout=TIMEOUT_ELEMENT * 2, state="visible"
                )
            except PlaywrightTimeoutError as exc:
                if "sign-up" in page.url:
                    raise RuntimeError(
                        "No BeatStars account found for that email"
                    ) from exc
                err = page.query_selector(SEL_LOGIN_ERROR)
                if err is not None:
                    msg = (err.inner_text() or "").strip()
                    raise RuntimeError(
                        f"BeatStars rejected the email: {msg or 'unknown error'}"
                    ) from exc
                raise

            page.fill(SEL_PASSWORD, password)
            page.click(SEL_LOGIN_SUBMIT, timeout=TIMEOUT_ELEMENT)

            # Login → redirect to studio.beatstars.com or dashboard
            try:
                page.wait_for_url(
                    lambda url: LOGGED_IN_HOST in url or "/dashboard" in url,
                    timeout=TIMEOUT_NAV,
                )
            except PlaywrightTimeoutError:
                pass  # check outcome below
        except PlaywrightTimeoutError as exc:
            # Capture a diagnostic to help debug selector/anti-bot issues
            diag = _capture_diagnostic(page, label="login")
            raise RuntimeError(
                "BeatStars login didn't complete — "
                f"selectors may have changed or bot detection is blocking us. "
                f"Diagnostic: {diag}"
            ) from exc

        outcome = _detect_login_outcome(page)
        if outcome == "sms":
            diag = _capture_diagnostic(page, label="sms")
            log.info("BeatStars SMS challenge detected: %s", diag)
            if sms_handler is None:
                raise RuntimeError(
                    "BeatStars is asking for an SMS verification code, but no "
                    "handler was provided to relay it. "
                    f"Diagnostic: {diag}"
                )
            hint = _read_sms_hint(page)
            sms_handler.on_detected(hint)

            code = sms_handler.get_code()
            if code is None or not code.strip():
                raise SmsCancelled("SMS challenge was cancelled or timed out")

            try:
                _submit_sms_code(page, code)
            except RuntimeError as exc:
                _capture_diagnostic(page, label="sms-submit-fail")
                raise RuntimeError(str(exc)) from exc

            # Re-evaluate: success, still SMS (wrong code), or other failure.
            outcome = _detect_login_outcome(page)
            if outcome == "sms":
                _capture_diagnostic(page, label="sms-rejected")
                raise RuntimeError(
                    "BeatStars rejected the verification code (or it expired). "
                    "Try connecting again to get a fresh code."
                )
        if outcome == "bad_credentials":
            diag = _capture_diagnostic(page, label="bad-creds")
            raise RuntimeError(f"Wrong BeatStars email or password (diagnostic: {diag})")
        if outcome == "captcha":
            diag = _capture_diagnostic(page, label="captcha")
            raise RuntimeError(
                f"BeatStars is showing a captcha. Diagnostic: {diag}"
            )
        if outcome != "success":
            diag = _capture_diagnostic(page, label="unknown")
            raise RuntimeError(
                f"BeatStars login failed for an unknown reason. Diagnostic: {diag}"
            )

        label = _read_account_label(page)
        storage = context.storage_state()
        return LoginResult(storage_state=storage, account_label=label)


# ─────────────────────────────────────────────────────────────────────────────
# Upload flow
# ─────────────────────────────────────────────────────────────────────────────


def _dismiss_onboarding(page: Page, *, timeout_ms: int = 12_000) -> None:
    """Close BeatStars's first-time-use onboarding carousel if it appears.

    The modal is rendered by Angular AFTER initial page load — typically 1-5s in.
    We wait up to 12s for it to appear. If it never does (e.g. cookies remember
    that we already dismissed it), we move on quickly via the timeout.

    Failures are swallowed — we never want to block an upload on this.
    """
    try:
        page.wait_for_selector(
            SEL_ONBOARDING_CLOSE, timeout=timeout_ms, state="visible"
        )
    except PlaywrightTimeoutError:
        log.info("No BeatStars onboarding carousel detected; proceeding")
        return

    try:
        page.click(SEL_ONBOARDING_CLOSE)
        # Wait for the modal to actually go away
        page.wait_for_selector(
            SEL_ONBOARDING_CLOSE, state="detached", timeout=5_000
        )
        page.wait_for_timeout(500)
        log.info("Dismissed BeatStars onboarding carousel")
    except Exception as exc:  # noqa: BLE001
        log.warning("Onboarding dismiss failed (continuing anyway): %s", exc)


def _set_chip(page: Page, input_selector: str, value: str) -> bool:
    """Add a single chip to a Material chip-input. Returns True on success.

    BeatStars uses two chip-input variants:
    - Free-text (tags): type, press Enter
    - Autocomplete-only (genre, mood, instruments): type, wait for dropdown, ArrowDown+Enter
    We try Enter first, fall back to ArrowDown+Enter for autocompletes.
    """
    try:
        page.click(input_selector, timeout=TIMEOUT_ELEMENT)
        page.fill(input_selector, value)
        # Give Angular's autocomplete a moment to populate
        page.wait_for_timeout(400)
        page.press(input_selector, "Enter")
        page.wait_for_timeout(200)
        # If the chip didn't stick (autocomplete-required field), try ArrowDown+Enter
        # We can't easily verify the chip appeared, so do both attempts.
        try:
            # If the input still has the typed text, the chip wasn't created
            current = page.input_value(input_selector)
            if current.strip():
                page.press(input_selector, "ArrowDown")
                page.wait_for_timeout(150)
                page.press(input_selector, "Enter")
        except Exception:
            pass
        return True
    except Exception:
        log.warning("Failed to set chip %r on %s", value, input_selector)
        return False


def _do_upload(
    storage_state: dict[str, Any] | None,
    file_path: Path,
    meta: BeatMetadata,
) -> tuple[UploadHandle | None, dict | None, bool]:
    """Returns (handle, fresh_storage, session_expired_flag).

    If session expired, returns (None, None, True) so caller can re-login + retry.
    """
    with browser_session(storage_state=storage_state) as (_, context):
        page = context.new_page()
        # Angular SPA — need to wait for the full app to render, not just DOM
        page.goto(UPLOAD_URL, wait_until="load", timeout=TIMEOUT_NAV)

        # Bounced to login = session dead
        if "/login" in page.url or "oauth.beatstars.com" in page.url:
            return None, None, True

        # BeatStars shows a 5-slide onboarding carousel the first time you hit
        # the upload page. It renders late (after Angular hydration), so the
        # dismiss has a generous timeout window.
        _dismiss_onboarding(page)

        # Uppy modal should open automatically (?create=true). The file input is
        # intentionally hidden (Uppy renders its own styled button), so wait for
        # the input to be ATTACHED in the DOM, not visible.
        try:
            page.wait_for_selector(
                ".uppy-Dashboard", timeout=TIMEOUT_NAV, state="attached"
            )
        except PlaywrightTimeoutError as exc:
            diag = _capture_diagnostic(page, label="upload-no-uppy")
            raise RuntimeError(
                f"BeatStars upload modal didn't appear. Diagnostic: {diag}"
            ) from exc
        page.wait_for_selector(SEL_UPPY_FILE_INPUT, timeout=TIMEOUT_ELEMENT, state="attached")

        # Drop all files in one shot — BeatStars's "smart upload" auto-categorizes
        # them into Master / Tagged / Stems slots by file extension. We build the
        # list from meta paths plus file_path (the "primary"), deduping so we
        # never upload the same file twice.
        seen: set[str] = set()
        files_to_upload: list[str] = []
        for candidate in (
            file_path,
            meta.master_path,
            meta.tagged_path,
            meta.stems_path,
        ):
            if candidate is None:
                continue
            s = str(candidate)
            if s in seen:
                continue
            seen.add(s)
            files_to_upload.append(s)
        page.set_input_files(SEL_UPPY_FILE_INPUT, files_to_upload)

        # Upload + transition to form. The title input is the canonical signal
        # that the form is ready — it only renders after the file is accepted.
        page.wait_for_selector(SEL_FORM_TITLE, timeout=TIMEOUT_UPLOAD, state="visible")
        # Give Angular a beat to wire up the form
        page.wait_for_timeout(800)

        # --- Required fields ---
        page.fill(SEL_FORM_TITLE, meta.title[:60])

        if meta.bpm is not None:
            try:
                page.fill(SEL_FORM_BPM, str(meta.bpm))
            except PlaywrightTimeoutError:
                log.warning("Couldn't fill BPM")

        key_enum = normalize_key(meta.music_key)
        if key_enum:
            try:
                page.select_option(SEL_FORM_KEY, key_enum)
            except Exception:
                log.warning("Couldn't set key to %s", key_enum)

        # Tags (free text, press Enter to confirm)
        for tag in clamp_tags(meta.tags or []):
            _set_chip(page, SEL_FORM_TAGS_INPUT, tag)

        # Cover art — best-effort, doesn't block publish on failure
        if meta.artwork_path is not None:
            _upload_artwork(page, meta.artwork_path)

        # Genre (optional on BeatStars, autocomplete-only). Only set it if the
        # user explicitly supplied one — no guessing, no defaults. BeatStars
        # carries genres across uploads, so leaving it untouched preserves
        # whatever was on the previous track.
        if meta.genre:
            _set_chip(page, SEL_FORM_GENRE_INPUT, meta.genre)

        # --- License selection ---
        # Detect roles from the explicit master/tagged/stems paths in meta —
        # don't rely on file_path because the "primary" might be the MP3 when
        # no WAV was uploaded.
        has_master_wav = meta.master_path is not None and meta.master_path.suffix.lower() in (
            ".wav",
            ".wave",
            ".flac",
        )
        has_tagged = meta.tagged_path is not None
        has_stems = meta.stems_path is not None
        license_choices = pick_licenses(
            meta.license_type,
            has_master_wav=has_master_wav,
            has_tagged=has_tagged,
            has_stems=has_stems,
        )
        # In AUTO mode the user's single price applies to the highest tier only
        # (Exclusive if present, else the last one); other tiers keep BeatStars
        # account defaults. If they explicitly picked a single license, that
        # license gets the price.
        is_auto = (meta.license_type or "AUTO") == "AUTO"
        priced_license = license_choices[-1] if license_choices else None
        for lic in license_choices:
            price = (
                meta.price_cents
                if (not is_auto or lic == priced_license)
                else None
            )
            _enable_license(page, lic, price_cents=price)

        # --- Publish ---
        page.click(SEL_PUBLISH_BUTTON, timeout=TIMEOUT_ELEMENT)

        # Success = the share dialog appears
        try:
            page.wait_for_selector(SEL_SUCCESS_DIALOG, timeout=TIMEOUT_NAV)
        except PlaywrightTimeoutError as exc:
            # Check for an inline validation error before giving up
            err = page.query_selector('[role="alert"], .form-error')
            if err is not None:
                msg = (err.inner_text() or "").strip()
                raise RuntimeError(
                    f"BeatStars rejected the upload: {msg or 'unknown form error'}"
                ) from exc
            raise RuntimeError(
                "BeatStars publish didn't complete — share dialog never appeared. "
                "Likely a required field (often genre) wasn't accepted."
            ) from exc

        # Pull the marketplace URL from the dialog
        public_url: str | None = None
        try:
            el = page.query_selector(SEL_SUCCESS_MARKETPLACE_LINK)
            if el is not None:
                public_url = el.get_attribute("value") or None
        except Exception:
            pass
        # Fall back to the current page URL if we can't read the share URL
        public_url = public_url or page.url

        fresh_state = context.storage_state()
        return (
            UploadHandle(
                external_id=public_url,
                public_url=public_url,
                session_data=fresh_state,
            ),
            fresh_state,
            False,
        )


def _close_cropper_if_open(page: Page) -> None:
    """If BeatStars's image-cropper dialog is open, confirm + close it.

    The cropper uses Cropper.js (`.cropper-modal`, `.cropper-drag-box`). It
    blocks all clicks behind it until you confirm or cancel — which is exactly
    what made the Publish button uncllickable before. Try to confirm first;
    fall back to dismissing so the publish can continue without artwork.
    """
    try:
        # No cropper → nothing to do
        if page.query_selector(".cropper-modal, .cropper-container") is None:
            return
        # Try common confirm-button labels inside any dialog overlay
        for text in ("Save", "Apply", "Done", "Confirm", "Crop", "Upload", "Submit"):
            try:
                btn = page.query_selector(
                    f'.cdk-overlay-container button:has-text("{text}"), '
                    f'mat-dialog-container button:has-text("{text}"), '
                    f'button.bs-btn:has-text("{text}")'
                )
                if btn is not None and btn.is_enabled():
                    btn.click()
                    page.wait_for_timeout(800)
                    if page.query_selector(".cropper-modal, .cropper-container") is None:
                        log.info("Closed cropper via '%s' button", text)
                        return
            except Exception:
                continue
        # Nothing worked — escape to dismiss (loses the artwork but unblocks publish)
        log.warning("Couldn't find cropper confirm button; dismissing dialog")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cropper close failed: %s", exc)


def _upload_artwork(page: Page, artwork_path: Path) -> bool:
    """Upload cover art to BeatStars's artwork component. Verified flow:

      1. Snapshot current artwork img.src (success signal)
      2. Click "Edit" dropdown next to the artwork image
      3. Click "Upload file" menu item → opens a Uppy dialog (image-only)
      4. set_input_files on the new Uppy input
      5. Wait for Uppy's green "Upload N file(s)" button to become enabled, click it
      6. Close BeatStars's post-upload Cropper.js modal if it appears
      7. Wait for img.track-form-artwork.src to change — confirms the new image landed

    Best-effort end-to-end. Logs at each step.
    """
    try:
        # 1. Capture the current artwork URL as a "before" snapshot
        before_img = page.query_selector(f'{SEL_ARTWORK_WRAPPER} img.track-form-artwork')
        before_src = before_img.get_attribute("src") if before_img is not None else None

        # 2. Open the Edit dropdown
        edit_btn = page.query_selector(SEL_ARTWORK_EDIT_BTN)
        if edit_btn is None:
            log.warning("Artwork Edit button not found; skipping cover art")
            return False
        edit_btn.click()
        page.wait_for_timeout(500)

        # 3. Click "Upload file" in the dropdown menu
        upload_item = None
        for selector in (
            '.cdk-overlay-container button:has-text("Upload file")',
            '.cdk-overlay-container [role="menuitem"]:has-text("Upload file")',
            '.cdk-overlay-container button:has-text("Upload")',
            'mat-menu-item:has-text("Upload")',
        ):
            try:
                el = page.query_selector(selector)
                if el is not None:
                    upload_item = el
                    break
            except Exception:
                continue
        if upload_item is None:
            log.warning("Artwork 'Upload file' menu item not found")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        upload_item.click()
        page.wait_for_timeout(800)

        # 4. Find the image-only Uppy file input in the newly-opened dialog
        try:
            page.wait_for_selector(
                'input.uppy-Dashboard-input[accept*="image"]:not([webkitdirectory])',
                timeout=TIMEOUT_ELEMENT,
                state="attached",
            )
        except PlaywrightTimeoutError:
            log.warning("Artwork Uppy dialog didn't open; skipping cover art")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        image_input = page.query_selector(
            'input.uppy-Dashboard-input[accept*="image"]:not([webkitdirectory])'
        )
        if image_input is None:
            log.warning("Image-accepting Uppy input not found")
            return False
        image_input.set_input_files(str(artwork_path))
        page.wait_for_timeout(800)

        # 5a. BeatStars's Uppy config auto-opens the FileEditor panel (with
        # cropper.js) when you drop a file. That cropper's `.cropper-modal`
        # intercepts all pointer events, blocking the "Upload N files" click
        # below. We dismiss the editor by clicking its top-bar Save button.
        editor_save = page.query_selector(
            '.uppy-DashboardContent-panel--editor button.uppy-DashboardContent-save, '
            '.uppy-DashboardContent-bar button.uppy-DashboardContent-save'
        )
        if editor_save is not None:
            try:
                editor_save.click()
                log.info("Closed Uppy image editor via its Save button")
                # Wait for the editor panel to detach so its cropper isn't intercepting
                page.wait_for_selector(
                    ".uppy-DashboardContent-panel--editor",
                    state="hidden",
                    timeout=10_000,
                )
            except PlaywrightTimeoutError:
                log.warning("Uppy editor didn't close after Save — continuing anyway")
            except Exception as exc:  # noqa: BLE001
                log.warning("Couldn't close Uppy editor: %s", exc)

        page.wait_for_timeout(400)

        # 5b. Wait for the upload commit button to be visible AND enabled
        try:
            page.wait_for_selector(
                'button.uppy-StatusBar-actionBtn--upload:not([disabled])',
                timeout=TIMEOUT_ELEMENT,
                state="visible",
            )
        except PlaywrightTimeoutError:
            log.warning("Uppy 'Upload' commit button never became enabled")
            return False

        commit_btn = page.query_selector('button.uppy-StatusBar-actionBtn--upload')
        if commit_btn is None:
            log.warning("Uppy upload button vanished before click")
            return False
        commit_btn.click()
        log.info("Clicked Uppy 'Upload' commit")

        # 6. Wait for BeatStars's post-upload cropper, confirm it
        page.wait_for_timeout(2500)
        _close_cropper_if_open(page)

        # 7. Confirm by checking the artwork img.src actually changed
        try:
            page.wait_for_function(
                """([sel, before]) => {
                    const img = document.querySelector(sel);
                    return img && img.src && img.src !== before;
                }""",
                arg=[f'{SEL_ARTWORK_WRAPPER} img.track-form-artwork', before_src],
                timeout=30_000,
            )
            log.info("Artwork successfully attached (img.src changed)")
            return True
        except PlaywrightTimeoutError:
            log.warning(
                "Artwork img.src never changed — upload may not have completed "
                "(or BeatStars still showing previous image)"
            )
            return False
    except Exception as exc:  # noqa: BLE001
        log.warning("Artwork upload failed: %s", exc)
        # Defensive: try to dismiss any orphan dialog so publish isn't blocked
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            _close_cropper_if_open(page)
        except Exception:
            pass
        return False


def _enable_license(page: Page, license_type: str, *, price_cents: int | None) -> None:
    """Enable a license toggle and optionally set its price.

    Waits up to 3 minutes for the license card to leave `prevent-enabling`
    (BeatStars holds it there until the required files finish processing).

    Then flips the toggle by directly clicking the hidden `<input role="switch">`
    via JS — clicking the outer `mat-slide-toggle` doesn't reliably register
    with Angular Material's change detection.
    """
    label = LICENSE_LABEL.get(license_type)
    if label is None:
        log.warning("Unknown license_type %r; skipping", license_type)
        return

    # Wait for files to process (card loses `prevent-enabling`)
    try:
        page.wait_for_function(
            """(label) => {
                const cards = Array.from(document.querySelectorAll('.license-card'));
                const card = cards.find(c => c.textContent.includes(label));
                return card && !card.classList.contains('prevent-enabling');
            }""",
            arg=label,
            timeout=TIMEOUT_UPLOAD,
        )
    except PlaywrightTimeoutError:
        log.warning(
            "License %r never lost prevent-enabling (files may still be processing).",
            license_type,
        )
        return

    # Flip the toggle by clicking the hidden checkbox input directly via JS.
    # Returns true if it flipped, false if not found or already on.
    result = page.evaluate(
        """(label) => {
            const cards = Array.from(document.querySelectorAll('.license-card'));
            const card = cards.find(c => c.textContent.includes(label));
            if (!card) return { ok: false, reason: 'card-not-found' };
            const input = card.querySelector('input[role="switch"]');
            if (!input) return { ok: false, reason: 'input-not-found' };
            if (input.checked) return { ok: true, reason: 'already-on' };
            input.click();  // bubbles through Material's change detection
            return { ok: true, reason: 'clicked' };
        }""",
        label,
    )
    if not result.get("ok"):
        log.warning(
            "Couldn't flip %s toggle: %s", license_type, result.get("reason")
        )
        return

    # Verify the card actually flipped to `enabled` (animation + change detection)
    try:
        page.wait_for_function(
            """(label) => {
                const cards = Array.from(document.querySelectorAll('.license-card'));
                const card = cards.find(c => c.textContent.includes(label));
                return card && card.classList.contains('enabled');
            }""",
            arg=label,
            timeout=10_000,
        )
        log.info("Enabled BeatStars %s license", license_type)
    except PlaywrightTimeoutError:
        log.warning(
            "Clicked %s toggle but card never got 'enabled' class — "
            "publish may go through with default license only",
            license_type,
        )
        # Don't return — still try to set price; worst case the price is set but
        # toggle isn't on, which the user can fix in BeatStars's UI.

    # Set custom price if requested
    if price_cents is not None and price_cents > 0:
        try:
            card = page.locator(SEL_LICENSE_CARD, has_text=label).first
            price_input = card.locator(SEL_LICENSE_PRICE_INPUT).first
            price_value = f"{price_cents / 100:.2f}"
            price_input.fill(price_value)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to set price on %s: %s", license_type, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Connector
# ─────────────────────────────────────────────────────────────────────────────


class BeatStarsConnector(PlatformConnector):
    provider = PlatformProvider.beatstars
    method = AuthMethod.headless
    display_name = "BeatStars"

    async def start_authorize(self, *, user_id: int, redirect_uri: str) -> OAuthRedirect:
        raise NotImplementedError(
            "BeatStars uses username/password — POST /api/platforms/beatstars/credentials"
        )

    async def complete_authorize(self, *, code: str, state: str, redirect_uri: str) -> dict:
        raise NotImplementedError("BeatStars uses username/password, not OAuth")

    async def disconnect(self, connection: PlatformConnection) -> None:
        return None

    async def login_and_capture_session(
        self,
        *,
        username: str,
        password: str,
        sms_handler: SmsHandler | None = None,
    ) -> LoginResult:
        return await asyncio.to_thread(
            _do_login, username, password, sms_handler=sms_handler
        )

    async def upload(
        self,
        connection: PlatformConnection,
        *,
        file_path: Path,
        meta: BeatMetadata,
        progress_cb: ProgressCallback | None = None,
    ) -> UploadHandle:
        # Default path: drive BeatStars over its private HTTP API (no browser).
        # Falls back to the Playwright flow below when BEATSTARS_USE_HTTP=false.
        from app.config import get_settings

        if get_settings().beatstars_use_http:
            from app.services.platforms import _beatstars_http

            return await _beatstars_http.upload(
                connection, file_path=file_path, meta=meta, progress_cb=progress_cb
            )

        storage: dict[str, Any] | None = None
        if connection.session_data_encrypted:
            try:
                storage = deserialize_storage_state(
                    decrypt_token(connection.session_data_encrypted)
                )
            except Exception:
                storage = None

        try:
            handle, _fresh, expired = await asyncio.to_thread(
                _do_upload, storage, file_path, meta
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                "BeatStars upload timed out — likely a selector mismatch. "
                "Inspect the upload page and update beatstars.py."
            ) from exc

        if expired:
            if not connection.account_label or not connection.access_token_encrypted:
                raise RuntimeError(
                    "BeatStars session expired and no stored credentials to re-login."
                )
            username = connection.account_label
            password = decrypt_token(connection.access_token_encrypted)
            login = await self.login_and_capture_session(
                username=username, password=password
            )
            handle, _fresh, expired = await asyncio.to_thread(
                _do_upload, login.storage_state, file_path, meta
            )
            if expired or handle is None:
                raise RuntimeError("BeatStars rejected the upload after re-login")

        if handle is None:
            raise RuntimeError("BeatStars upload returned no handle")
        return handle

    async def poll(self, connection: PlatformConnection, handle: UploadHandle) -> UploadProgress:
        return UploadProgress(progress=100, status="done", public_url=handle.public_url)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers used by the API layer
# ─────────────────────────────────────────────────────────────────────────────


async def connect_with_credentials(
    *,
    username: str,
    password: str,
    sms_handler: SmsHandler | None = None,
) -> tuple[str, str, str]:
    """Validate credentials by logging in. Returns (encrypted_password, encrypted_session, label).

    If ``sms_handler`` is provided and BeatStars challenges us with 2FA, the
    handler bridges the code between the API endpoint and this login thread.
    (SMS only applies to the Playwright path; the HTTP password grant doesn't
    trigger it, so ``sms_handler`` is ignored there.)
    """
    from app.config import get_settings

    if get_settings().beatstars_use_http:
        from app.services.platforms import _beatstars_http

        return await _beatstars_http.connect_with_credentials(
            username=username, password=password
        )

    connector = BeatStarsConnector()
    result = await connector.login_and_capture_session(
        username=username, password=password, sms_handler=sms_handler
    )
    return (
        encrypt_token(password),
        encrypt_token(serialize_storage_state(result.storage_state)),
        result.account_label or username,
    )
