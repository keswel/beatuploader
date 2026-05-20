"""Outbound transactional email.

In dev (no SMTP_HOST configured) emails are written to the log so you can grab
the password-reset link from the terminal without standing up a real provider.
In prod, set SMTP_HOST/PORT/USER/PASSWORD/FROM and we'll send over STARTTLS.

Stdlib `smtplib` (sync) wrapped in `asyncio.to_thread` — keeps the dep list
small and avoids pinning a specific transactional provider. Swap for
`aiosmtplib` or a provider SDK later if you outgrow it.
"""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

log = logging.getLogger(__name__)


def _send_sync(*, to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.ehlo()
        # STARTTLS is the modern default for port 587. If you need implicit TLS
        # (port 465), swap for smtplib.SMTP_SSL.
        smtp.starttls()
        if s.smtp_user and s.smtp_password:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


async def send_email(*, to: str, subject: str, body: str) -> None:
    """Send a plaintext email. Never raises — failures are logged.

    Logged-not-raised because email is a side effect of user actions (password
    reset, etc.); we don't want a transient SMTP outage to fail their core
    flow. The caller's contract is "email may take a while or never arrive";
    don't depend on send_email for security guarantees.
    """
    s = get_settings()
    if not s.smtp_host:
        # Dev path. Log the whole body so you can grab reset links from stdout.
        log.info(
            "[email:stdout] to=%s subject=%s\n----- body -----\n%s\n----- /body -----",
            to,
            subject,
            body,
        )
        return

    try:
        await asyncio.to_thread(_send_sync, to=to, subject=subject, body=body)
        log.info("Sent email to %s (%s)", to, subject)
    except Exception:
        log.exception("Failed to send email to %s (%s)", to, subject)
