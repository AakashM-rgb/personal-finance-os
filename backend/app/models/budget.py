"""Budget models.

`Budget` is a lightweight, one-per-user container - auto-created
transparently the first time a user creates a budget item (see
app.services.budget_service) and never exposed as a resource of its own;
users only ever see/manage `BudgetItem` rows via the API.

`BudgetItem` deletion is a real hard delete, unlike Account/Category/
Transaction: nothing else in the schema references a budget_item_id, so
there is no historical-integrity reason to soft-delete it.
"""

import uuid

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    items: Mapped[list["BudgetItem"]] = relationship(
        back_populates="budget", cascade="all, delete-orphan"
    )


class BudgetItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budget_items"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_budget_items_amount_positive"),
        UniqueConstraint("budget_id", "category_id", name="uq_budget_items_budget_category"),
    )

    budget_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("budgets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The monthly spending limit for this category - always in the
    # account/transaction currency convention (integer minor units).
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)

    budget: Mapped["Budget"] = relationship(back_populates="items")
