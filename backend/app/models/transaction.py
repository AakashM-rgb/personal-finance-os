"""Transaction model - the core ledger.

`amount_minor` is always a positive magnitude in integer minor units; the
sign is implied by `type`, never stored as a negative number, so a bug can
never silently flip a transaction's effect by misreading a sign.

Transfers move money between two of the user's own accounts and must never
be counted as income or expense - `type` is a first-class enum (not a
boolean flag) precisely so every query that sums income/expense can exclude
transfers by construction, and `category_id`/`transfer_account_id` are
mutually exclusive by validation (see app.schemas.transaction).

`currency` is never user-supplied - it is copied from the account's currency
at the moment the transaction is created (see
app.services.transaction_service), so it can never mismatch the account's
own currency. It is still stored on the row (not derived live from the
account on every read) because the account's currency can be edited later;
a transaction must keep recording what currency it actually happened in,
not whatever the account's currency happens to be today.

`recurring_transaction_id` links a generated occurrence back to its
schedule template (see app.models.recurring_transaction). The unique
constraint on (recurring_transaction_id, occurred_at) is the database-level
half of the recurring-generation idempotency guarantee described in
CLAUDE.md §4 - Postgres treats multiple NULLs as distinct, so ordinary
(non-generated) transactions never collide with each other on it.

`linked_account_id`/`external_transaction_id` link a transaction back to the
`LinkedAccount` (see app.models.linked_account) and provider-side identifier
it was ingested from, for a future automatic-sync feature. As with the
recurring-generation pair above, the actual create-time idempotency
guarantee for synced transactions is expected to reuse the existing
`idempotency_key` mechanism above (e.g. a key derived from the linked
account and external transaction id); the partial unique index on these two
columns is a defense-in-depth backstop, not the primary mechanism, and never
applies to ordinary (non-synced) transactions since it only covers rows
where `linked_account_id IS NOT NULL`. No ingestion logic exists yet - these
columns are additive schema only.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class TransactionType(enum.StrEnum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_transactions_amount_positive"),
        CheckConstraint(
            "(type = 'transfer' AND transfer_account_id IS NOT NULL AND category_id IS NULL)"
            " OR (type != 'transfer' AND transfer_account_id IS NULL)",
            name="ck_transactions_transfer_shape",
        ),
        Index("ix_transactions_user_occurred_at", "user_id", "occurred_at"),
        Index("ix_transactions_user_account", "user_id", "account_id"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
        # Postgres treats multiple NULLs as distinct, so requests with no
        # idempotency key never collide with each other.
        UniqueConstraint("user_id", "idempotency_key", name="uq_transactions_user_idempotency_key"),
        # The database-level backstop for idempotent recurring generation -
        # see the module docstring.
        UniqueConstraint(
            "recurring_transaction_id",
            "occurred_at",
            name="uq_transactions_recurring_occurrence",
        ),
        # Defense-in-depth backstop for synced transactions - see the module
        # docstring. Postgres partial indexes never evaluate NULLs against
        # the predicate, so ordinary (non-synced) transactions are entirely
        # unaffected by this constraint.
        Index(
            "uq_transactions_linked_account_external_id",
            "linked_account_id",
            "external_transaction_id",
            unique=True,
            postgresql_where=text("linked_account_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    # Destination account - transfers only.
    transfer_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # SET NULL (not CASCADE): deleting the recurring template must never
    # delete the real transactions it already generated - it only detaches
    # them into ordinary standalone transactions.
    recurring_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("recurring_transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    type: Mapped[TransactionType] = mapped_column(
        str_enum_column(TransactionType, name="transaction_type"),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)

    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tags: Mapped[list[str]] = mapped_column(PG_ARRAY(String(50)), nullable=False, default=list)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # A manual flag only for now - no recurring_transaction_id FK yet, since
    # the recurring-transactions table doesn't exist until a later phase.
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Lets offline/PWA clients safely retry a create without double-booking it.
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Automatic sync provenance - see the module docstring. Both remain NULL
    # for every manual, recurring-generated, and receipt-derived transaction.
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_transaction_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
