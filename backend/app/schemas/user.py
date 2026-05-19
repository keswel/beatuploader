from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    handle: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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
    current_password: str | None = None  # None allowed when user has no password (Google-only)
    new_password: str = Field(min_length=8, max_length=128)


class AccountDelete(BaseModel):
    # User must type their handle to confirm. Mismatch = 400.
    confirm_handle: str
