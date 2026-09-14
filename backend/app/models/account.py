"""Account model.

`balance_minor` is the account's current balance in integer minor units
(paise) - never a float. For a credit card account, this represents the
current amount owed (usage), maintained manually until the transactions
module can derive it from the ledger.
"""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column

if TYPE_CHECKING:
    from app.models.credit_card_details import CreditCardDetails


class AccountType(enum.StrEnum):
    BANK_ACCOUNT = "bank_account"
    CASH = "cash"
    CREDIT_CARD = "credit_card"
    UPI = "upi"
    SAVINGS_ACCOUNT = "savings_account"
    WALLET = "wallet"


class Account(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[AccountType] = mapped_column(
        str_enum_column(AccountType, name="account_type"),
        nullable=False,
    )
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    institution_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Soft-delete: an "archived" account is hidden from default lists but its
    # id remains valid, since a future transactions ledger will reference
    # account_id and must never be able to point at a vanished row.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    credit_card: Mapped["CreditCardDetails | None"] = relationship(
        back_populates="account", uselist=False, cascade="all, delete-orphan"
    )
