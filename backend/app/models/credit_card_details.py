"""Credit-card-specific fields, 1:1 extension of an Account with type=CREDIT_CARD.

Kept as a separate table rather than bloating the base `accounts` row with
columns that only apply to one account type.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.account import Account


class CreditCardDetails(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "credit_card_details"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    credit_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Day of the billing cycle (1-31), not a calendar date - the same value
    # applies every statement cycle until the user changes it.
    statement_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payment_due_day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Manually tracked until a statement/billing engine exists - there is no
    # transaction history yet to derive this from.
    minimum_payment_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="credit_card")
