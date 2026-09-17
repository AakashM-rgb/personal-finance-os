"""Category model.

`user_id = NULL` means a system default category, seeded once and shared by
every user (read-only for users - they can never edit or delete these).
`user_id = <uuid>` means a custom category owned by that user, fully
editable/deletable by them and invisible to everyone else.
"""

import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        # Only constrains a user's own active categories - system rows
        # (user_id IS NULL) are untouched by this index, and an archived
        # (is_active=False) category's name frees up for reuse rather than
        # permanently blocking it. The real backstop against a concurrent
        # duplicate create is this DB constraint, not the service-layer
        # pre-check (see app.services.category_service).
        Index(
            "uq_categories_user_name_active",
            "user_id",
            "name",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL AND is_active = true"),
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    # Optional suggested/default monthly budget for this category - distinct
    # from the full budgets/budget_items module (a later phase), which can
    # read this as a starting default when a user creates a real budget.
    budget_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    parent: Mapped["Category | None"] = relationship(
        remote_side="Category.id", back_populates="children"
    )
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
