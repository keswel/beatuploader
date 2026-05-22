"""Tests for password hashing and token encryption primitives."""

import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    decrypt_token,
    encrypt_token,
    hash_password,
    verify_password,
)


def test_hash_password_verifies() -> None:
    h = hash_password("Str0ng!Password")
    assert verify_password("Str0ng!Password", h)
    assert not verify_password("Str0ng!Passwordz", h)


def test_hash_password_truncates_long_input() -> None:
    # bcrypt truncates inputs to 72 bytes. Two passwords that differ only past
    # byte 72 must verify against the same hash — that's the documented bcrypt
    # behavior and our truncation matches it.
    base = "A!a1" + "x" * 80
    h = hash_password(base)
    assert verify_password(base[:72], h)
    assert verify_password(base + "EXTRA", h)


def test_verify_password_handles_garbage_hash() -> None:
    # bcrypt raises ValueError on malformed hashes; verify_password swallows
    # that and returns False so callers don't crash on DB corruption / bad
    # migration data.
    assert verify_password("anything", "not-a-real-hash") is False


def test_create_decode_roundtrip() -> None:
    token = create_access_token(subject="42", extra={"purpose": "test"})
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["purpose"] == "test"
    assert "iat" in payload  # load-bearing for password-change revocation


def test_decode_rejects_invalid_token() -> None:
    with pytest.raises(ValueError):
        decode_access_token("not-a-jwt")


def test_encrypt_decrypt_token_roundtrip() -> None:
    enc = encrypt_token("secret-value")
    assert enc != "secret-value"
    assert decrypt_token(enc) == "secret-value"


def test_decrypt_token_rejects_garbage() -> None:
    with pytest.raises(RuntimeError):
        decrypt_token("definitely-not-fernet")
