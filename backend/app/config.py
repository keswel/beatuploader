from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


DEV_JWT_SECRET = "dev-only-change-me"
# Valid Fernet key (base64 of "dev-only-change-me-32-bytes-base") — same derivation
# the old security code produced from the previous dev default, so tokens encrypted
# pre-upgrade still decrypt. THIS IS DEV-ONLY; prod must set its own.
DEV_TOKEN_ENCRYPTION_KEY = "ZGV2LW9ubHktY2hhbmdlLW1lLTMyLWJ5dGVzLWJhc2U="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # `debug=True` is dev-mode — relaxes secret-strength checks and surfaces
    # more error detail. Defaults to True for smooth local onboarding; MUST
    # be False in production for real users.
    debug: bool = True

    database_url: str = "sqlite+aiosqlite:///./beatuploader.db"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    backend_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    token_encryption_key: str = DEV_TOKEN_ENCRYPTION_KEY

    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    soundcloud_client_id: str = ""
    soundcloud_client_secret: str = ""

    storage_dir: str = Field(default="./storage")

    # OAuth state JWT lifetime (security: short window between start and callback)
    oauth_state_expire_seconds: int = 600

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    _validate_secrets(s)
    return s


def _validate_secrets(s: Settings) -> None:
    """Refuse to boot in prod if secrets are at their dev defaults or obviously weak.

    In debug mode we only warn — useful for first-run setups before the user has
    generated proper secrets. In prod (`DEBUG=false`), missing/weak secrets are
    fatal because they'd silently expose every encrypted token and every JWT.
    """
    import logging

    log = logging.getLogger(__name__)
    problems: list[str] = []

    if s.jwt_secret == DEV_JWT_SECRET or len(s.jwt_secret) < 32:
        problems.append(
            "JWT_SECRET is unset or too short (need >= 32 chars). "
            "Generate: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    if s.token_encryption_key == DEV_TOKEN_ENCRYPTION_KEY:
        problems.append(
            "TOKEN_ENCRYPTION_KEY is unset. Generate: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    else:
        # A real Fernet key is 32 url-safe-base64 bytes (= 44 chars including padding).
        from cryptography.fernet import Fernet

        try:
            Fernet(s.token_encryption_key.encode())
        except Exception:
            problems.append(
                "TOKEN_ENCRYPTION_KEY isn't a valid Fernet key. Generate: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

    if not problems:
        return
    if s.debug:
        for p in problems:
            log.warning("INSECURE CONFIG (debug mode tolerated): %s", p)
        return
    msg = "Refusing to boot — insecure config:\n  - " + "\n  - ".join(problems)
    raise RuntimeError(msg)
