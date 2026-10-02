"""Desktop-mode secret storage.

The Fernet key that encrypts platform tokens in the local SQLite DB lives in
the OS credential vault (Windows Credential Manager / macOS Keychain) via
`keyring` — never next to the DB it protects. If the vault is unavailable
(rare: locked-down Linux without a secret service), we fall back to a key file
in the data dir and log a warning.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import Fernet

log = logging.getLogger(__name__)

_SERVICE = "Beatuploader"
_KEY_NAME = "token-encryption-key"
_FALLBACK_FILE = "token-encryption.key"


def _valid(key: str | None) -> bool:
    if not key:
        return False
    try:
        Fernet(key.encode())
    except Exception:
        return False
    return True


def get_or_create_encryption_key(data_dir: Path) -> str:
    try:
        import keyring

        key = keyring.get_password(_SERVICE, _KEY_NAME)
        if _valid(key):
            return key  # type: ignore[return-value]
        key = Fernet.generate_key().decode()
        keyring.set_password(_SERVICE, _KEY_NAME, key)
        return key
    except Exception:
        log.warning(
            "OS credential vault unavailable — storing the encryption key in the data dir",
            exc_info=True,
        )

    path = data_dir / _FALLBACK_FILE
    if path.exists():
        key = path.read_text(encoding="utf-8").strip()
        if _valid(key):
            return key
    key = Fernet.generate_key().decode()
    path.write_text(key, encoding="utf-8")
    return key
