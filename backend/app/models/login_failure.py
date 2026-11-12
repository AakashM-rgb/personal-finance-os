"""One failed login attempt, keyed by account - backs the per-account login
throttle (app.services.login_throttle).

Deliberately not user-owned and with no FK to `users`: attempts against
emails that have no account are throttled exactly like real ones (otherwise
the throttle itself would reveal which emails are registered), so a row can't
reference a user. The email is never stored - only a keyed HMAC of it (see
login_throttle.account_key), which can't be reversed by guessing emails
without the server's secret. Rows are only useful inside the throttle window
and are pruned after it.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin


class LoginFailure(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "login_failures"
    __table_args__ = (
        Index("ix_login_failures_account_key_created_at", "account_key", "created_at"),
    )

    account_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
