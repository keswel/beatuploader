import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()

# bcrypt has a hard 72-byte input limit; truncate explicitly so long passwords
# don't blow up. Standard practice — see https://github.com/pyca/bcrypt#maximum-password-length
_BCRYPT_MAX_BYTES = 72


def _prep(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prep(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prep(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, Any] = {"sub": subject, "exp": expire, "iat": datetime.now(UTC)}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


def _fernet() -> Fernet:
    """Fernet instance from TOKEN_ENCRYPTION_KEY.

    The key MUST be a valid Fernet key (44 chars, url-safe base64 encoding of
    32 random bytes). Settings validation rejects invalid keys at startup, so
    by the time this runs we should be fine — but we still raise loudly if
    not, rather than silently deriving a weak key from whatever was provided.
    """
    return Fernet(settings.token_encryption_key.encode())


def encrypt_token(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_token(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except Exception as exc:
        # Don't leak whether it's a malformed token vs. rotated key etc.
        raise RuntimeError(
            "Couldn't decrypt stored credential — TOKEN_ENCRYPTION_KEY may "
            "have rotated. Reconnect the platform."
        ) from exc


# silence unused-import on Python without base64 use after refactor
_ = base64
