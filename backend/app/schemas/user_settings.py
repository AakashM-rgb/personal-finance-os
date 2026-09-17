"""Per-user settings request/response schemas.

`notification_preferences` is deliberately not exposed here - no notification
dispatcher reads it yet (see CLAUDE.md's "never create fake functionality"),
so it stays an internal-only column until that system exists.
"""

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.account import SUPPORTED_CURRENCIES

ALLOWED_THEMES = {"system", "light", "dark"}


class UserSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    theme: str
    ai_enabled: bool


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str | None = None
    theme: str | None = None
    ai_enabled: bool | None = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is not None and value not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return value

    @field_validator("theme")
    @classmethod
    def validate_theme(cls, value: str | None) -> str | None:
        if value is not None and value not in ALLOWED_THEMES:
            raise ValueError(f"theme must be one of {sorted(ALLOWED_THEMES)}")
        return value
