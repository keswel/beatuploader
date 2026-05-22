"""Tests for the server-side password complexity policy.

The same policy applies to register, change-password, and reset-password —
verified by exercising `_validate_password` directly. The endpoint tests in
test_auth.py cover the wiring.
"""

import pytest
from pydantic import ValidationError

from app.schemas.user import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    PasswordChange,
    PasswordResetConfirm,
    UserRegister,
)


VALID = "Str0ng!Password"


@pytest.mark.parametrize(
    "password,reason",
    [
        ("Aa1!", "too short"),
        ("A" * (PASSWORD_MAX_LENGTH + 1), "too long"),
        ("lowercase1!", "no uppercase"),
        ("UPPERCASE1!", "no lowercase"),
        ("NoDigits!", "no digit"),
        ("NoSpecial1", "no special character"),
    ],
)
def test_register_rejects_weak_passwords(password: str, reason: str) -> None:
    with pytest.raises(ValidationError):
        UserRegister(email="a@b.com", handle="user", password=password)


def test_register_accepts_strong_password() -> None:
    u = UserRegister(email="a@b.com", handle="user", password=VALID)
    assert u.password == VALID


def test_password_change_rejects_weak_new_password() -> None:
    with pytest.raises(ValidationError):
        PasswordChange(current_password="anything", new_password="weak")


def test_password_change_accepts_strong_new_password() -> None:
    pc = PasswordChange(current_password="anything", new_password=VALID)
    assert pc.new_password == VALID


def test_password_reset_rejects_weak_new_password() -> None:
    with pytest.raises(ValidationError):
        PasswordResetConfirm(token="abc", new_password="weak")


def test_password_min_length_boundary() -> None:
    # Exactly at the minimum with all classes present should pass.
    pwd = "A" + "a" * (PASSWORD_MIN_LENGTH - 4) + "1!a"
    assert len(pwd) >= PASSWORD_MIN_LENGTH
    UserRegister(email="a@b.com", handle="user", password=pwd)
