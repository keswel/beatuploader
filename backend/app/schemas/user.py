from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# Password policy. Enforced server-side on both register and change-password.
# Frontend has a matching validator (frontend/src/lib/password.ts) for inline UX.
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
_PASSWORD_SPECIALS = r"!@#$%^&*()-_=+[]{};:,.<>/?\|`~'\""


def _validate_password(value: str) -> str:
    """Strong-password rule: 8+ chars, upper, lower, digit, special.

    Length max matches the column + bcrypt's effective 72-byte limit (we truncate
    in security.hash_password, so longer is accepted but truncated — capping at
    128 here keeps the API contract honest).
    """
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must include at least one uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must include at least one lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must include at least one digit.")
    if not any(c in _PASSWORD_SPECIALS for c in value):
        raise ValueError("Password must include at least one special character.")
    return value


class UserRegister(BaseModel):
    email: EmailStr
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password(v)


class UserLogin(BaseModel):
    email: EmailStr
    # Login doesn't run the complexity check (existing weaker passwords still
    # need to authenticate). We cap length to prevent oversized payload DoS.
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    handle: str
    plan: str
    youtube_description_template: str | None = None
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserUpdate(BaseModel):
    handle: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    # Omit the key to leave unchanged. Include the key with null or "" to clear.
    youtube_description_template: str | None = Field(default=None, max_length=5000)


class PasswordChange(BaseModel):
    current_password: str | None = Field(default=None, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password(v)


class AccountDelete(BaseModel):
    # User must type their handle to confirm. Mismatch = 400.
    confirm_handle: str = Field(max_length=64)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=1, max_length=2048)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_password(v)
