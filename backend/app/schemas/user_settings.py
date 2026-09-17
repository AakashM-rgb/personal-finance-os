"""Per-user settings request/response schemas."""

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.account import SUPPORTED_CURRENCIES

ALLOWED_THEMES = {"system", "light", "dark"}


class NotificationPreferences(BaseModel):
    """One boolean per notification category app.services.notification_service
    actually generates (see that module for what each one gates) -
    `extra="forbid"` so an unrecognized field is rejected outright rather
    than silently stored and ignored forever. Every field defaults to
    True: notifications are useful by default (PRODUCT_SPEC.md §35), and a
    user opts individual categories out rather than opting the whole
    feature in."""

    model_config = ConfigDict(extra="forbid")

    budget_warnings: bool = True
    payment_reminders: bool = True
    goal_milestones: bool = True
    unusual_spending: bool = True
    recurring_reminders: bool = True


class UserSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    theme: str
    ai_enabled: bool
    notification_preferences: NotificationPreferences

    @field_validator("notification_preferences", mode="before")
    @classmethod
    def _default_missing_preferences(cls, value: dict | None) -> dict:
        # Existing rows created before this feature existed have
        # notification_preferences={} (the column's own default) - treated
        # as "every category still on its own default", never as invalid.
        return value or {}


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str | None = None
    theme: str | None = None
    ai_enabled: bool | None = None
    # A partial patch: only the categories present are changed, exactly
    # like every other field on this schema - see
    # app.services.user_settings_service.update_settings.
    notification_preferences: dict[str, bool] | None = None

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

    @field_validator("notification_preferences")
    @classmethod
    def validate_notification_preferences(
        cls, value: dict[str, bool] | None
    ) -> dict[str, bool] | None:
        if value is None:
            return None
        # Validated against the strict schema (extra="forbid", bool fields
        # only) rather than accepted as a raw dict - an unknown key or a
        # non-boolean value must be rejected here, before it ever reaches
        # the stored JSONB column, not silently merged in.
        NotificationPreferences.model_validate(value)
        return value
