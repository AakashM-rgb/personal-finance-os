"""Authentication request/response schemas."""

import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.user import UserRead

_PASSWORD_MIN_LENGTH = 8


def _validate_password_strength(value: str) -> str:
    if len(value) < _PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {_PASSWORD_MIN_LENGTH} characters long.")
    if not re.search(r"[A-Za-z]", value):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"\d", value):
        raise ValueError("Password must contain at least one number.")
    return value


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return _validate_password_strength(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
