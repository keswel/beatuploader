"""Tests for the DATABASE_URL normalization in app.db.

The deployment surface for this is wide — Render hands out one URL shape,
Heroku another, dev uses sqlite — so a few targeted unit tests beat one
fragile integration test.
"""

from app.db import _async_database_url


def test_sqlite_gets_aiosqlite_driver() -> None:
    assert (
        _async_database_url("sqlite:///./local.db")
        == "sqlite+aiosqlite:///./local.db"
    )


def test_sqlite_already_async_passthrough() -> None:
    url = "sqlite+aiosqlite:///./local.db"
    assert _async_database_url(url) == url


def test_postgres_legacy_scheme_gets_asyncpg() -> None:
    out = _async_database_url("postgres://u:p@host:5432/db")
    assert out == "postgresql+asyncpg://u:p@host:5432/db"


def test_postgresql_gets_asyncpg() -> None:
    out = _async_database_url("postgresql://u:p@host:5432/db")
    assert out == "postgresql+asyncpg://u:p@host:5432/db"


def test_postgres_strips_libpq_sslmode_query() -> None:
    # asyncpg silently ignores libpq query params like sslmode. If we left it
    # in, the connection would happily fall back to plaintext on a TLS-only
    # server. Strip it here so the asyncpg default kicks in.
    out = _async_database_url(
        "postgres://u:p@host:5432/db?sslmode=require&application_name=foo"
    )
    assert "sslmode" not in out
    assert "application_name=foo" in out  # non-libpq params preserved


def test_postgres_strips_multiple_libpq_params() -> None:
    out = _async_database_url(
        "postgresql://u:p@host:5432/db"
        "?sslmode=require&channel_binding=prefer&target_session_attrs=read-write"
    )
    for libpq in ("sslmode", "channel_binding", "target_session_attrs"):
        assert libpq not in out
