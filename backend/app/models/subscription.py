"""Subscription model - a 1:1 extension of RecurringTransaction (see
CLAUDE.md §4: "Subscriptions are a 1:1 extension of recurring_transactions,
not a parallel scheduler"), the same pattern CreditCardDetails uses to
extend Account.

A subscription IS a recurring transaction - all of its schedule, amount,
account, category, and generation behavior come from the underlying
RecurringTransaction (always type=expense; see
app.schemas.subscription). This table's only job is marking that a
particular recurring transaction is managed as a subscription in the
Subscription Manager UI, distinct from an ordinary recurring bill. It has
no columns of its own beyond the link, exactly like CreditCardDetails
would have none if credit cards needed no extra fields - the table exists
because the *relationship* is real, not because there is denormalized
data to store.

CASCADE: deleting the underlying recurring transaction deletes this
marker row too (there is nothing left to "manage as a subscription"
without it) - this is the reverse of Transaction's relationship to
RecurringTransaction, which detaches (SET NULL) rather than cascades,
because real transaction history must survive; there is no equivalent
history concern here.
"""

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    recurring_transaction_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("recurring_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
