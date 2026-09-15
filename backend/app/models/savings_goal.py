"""Savings goal model.

A savings goal is a directly user-owned entity - unlike Budget it needs no
one-per-user container, since a user can freely have any number of goals.
Deletion is a real hard delete, same reasoning as BudgetItem: nothing else
in the schema references a savings_goal_id, so there is no
historical-integrity reason to soft-delete it.

`current_amount_minor` can never exceed `target_amount_minor` - the
product does not support overfunded goals - enforced both here (a DB
check constraint, defense in depth) and in app.services.savings_goal_service.
"""

import uuid
from datetime import date

from sqlalchemy import BigInteger, CheckConstraint, Date, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SavingsGoal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "savings_goals"
    __table_args__ = (
        CheckConstraint("target_amount_minor > 0", name="ck_savings_goals_target_positive"),
        CheckConstraint(
            "current_amount_minor >= 0", name="ck_savings_goals_current_non_negative"
        ),
        CheckConstraint(
            "current_amount_minor <= target_amount_minor",
            name="ck_savings_goals_current_not_over_target",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    target_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    current_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
