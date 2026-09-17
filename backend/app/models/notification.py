"""Notification model.

A notification is always generated server-side from real, already-stored
data (a budget crossing a threshold, a goal hitting a milestone, an
upcoming subscription/credit-card/recurring-expense date, or a flagged
transaction) - never user-supplied, never random. See
app.services.notification_service for the generation logic and
app.services.notification_calculations for the deterministic rules behind
each category.

`dedupe_key` is the idempotency mechanism: each detector builds a
deterministic string that identifies the specific real-world event a
notification is about (e.g. "budget_warning:<budget_item_id>:2026-09" -
one per budget per month, or "unusual_spending:<transaction_id>" - one per
flagged transaction, ever). The unique constraint on (user_id, dedupe_key)
is the actual backstop that prevents re-running generation from ever
creating a duplicate - the same pattern this app already uses for
recurring-transaction generation (see
uq_transactions_recurring_occurrence on Transaction).

`reference_type`/`reference_id` are a generic, non-FK pointer to whatever
real entity the notification is about (a budget item, a goal, a
subscription, an account, a recurring transaction, or a transaction) -
the same deliberately-generic, string-typed pattern app.models.audit_log
already uses for its entity_type/entity_id, since a single FK column can't
point at six different tables.
"""

import enum
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class NotificationCategory(enum.StrEnum):
    BUDGET_WARNING = "budget_warning"
    BUDGET_EXCEEDED = "budget_exceeded"
    SUBSCRIPTION_REMINDER = "subscription_reminder"
    CREDIT_CARD_REMINDER = "credit_card_reminder"
    GOAL_MILESTONE = "goal_milestone"
    UNUSUAL_SPENDING = "unusual_spending"
    RECURRING_REMINDER = "recurring_reminder"


class Notification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe_key"),
        Index("ix_notifications_user_created_at", "user_id", "created_at"),
        Index("ix_notifications_user_is_read", "user_id", "is_read"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category: Mapped[NotificationCategory] = mapped_column(
        str_enum_column(NotificationCategory, name="notification_category", length=30),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)

    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action_url: Mapped[str | None] = mapped_column(String(200), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
