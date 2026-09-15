"""Recurring transaction model.

A recurring transaction is a schedule template - it never represents
money moving by itself. Each due occurrence materializes as a real
`Transaction` row (see app.services.recurring_transaction_service),
linked back via `Transaction.recurring_transaction_id`. Idempotency
across repeated generation runs is enforced at the database level by a
unique constraint on (recurring_transaction_id, occurred_at) on
`Transaction` itself (see app.models.transaction), not just by
application discipline - the application layer additionally never asks
to generate an occurrence date it can already see in the ledger (see
the service), so the constraint should never actually be hit in normal
operation; it exists as a backstop against a concurrent double-trigger.

Only income and expense recurring transactions are supported - transfers
are not, since nothing elsewhere in this architecture models a recurring
transfer (see CLAUDE.md §4).

`day_of_month` is fixed at creation from `start_date`'s day and never
changes afterward, so a "31st of every month" schedule stays anchored to
the 31st (or a shorter month's last day) forever, rather than drifting to
whatever day a clamped occurrence happened to land on. See
app.services.recurrence for the date math this anchor feeds into.
"""

import enum
import uuid
from datetime import date

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column
from app.models.transaction import TransactionType


class RecurrenceFrequency(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class RecurringTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recurring_transactions"
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0", name="ck_recurring_transactions_amount_positive"
        ),
        CheckConstraint(
            "type IN ('income', 'expense')",
            name="ck_recurring_transactions_type_not_transfer",
        ),
        CheckConstraint(
            "day_of_month >= 1 AND day_of_month <= 31",
            name="ck_recurring_transactions_day_of_month",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        str_enum_column(TransactionType, name="recurring_transaction_type"),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    frequency: Mapped[RecurrenceFrequency] = mapped_column(
        str_enum_column(RecurrenceFrequency, name="recurrence_frequency"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Fixed at creation from start_date.day - see the module docstring.
    day_of_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
