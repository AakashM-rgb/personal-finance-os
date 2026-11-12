"""Merchant category rule model - a user's persistent "always categorize
this merchant as..." memory (see app.services.merchant_rule_service).

`merchant_key` is always the CANONICAL value
app.services.merchant_normalization.normalize_merchant produces - never a
raw narration, and never a second, parallel normalization scheme. This is
what lets a rule learned from one synced transaction
("UPI/DR/399/SWIGGY/...") apply to a differently-worded future one
("UPI/DR/450/SWIGGY INSTAMART/...") - both normalize to the same key.

A rule is pure user preference data, not a ledger record: it carries no
provenance/audit trail of its own and is hard-deleted when the user
removes it (unlike a Transaction, which is never silently discarded).
`ondelete="CASCADE"` on both foreign keys reflects that a rule has no
meaning without its owner or its target category - categories are never
actually hard-deleted in this application (see app.services.category_service
- archiving only ever sets is_active=False), so this is a defensive
invariant rather than a path the app exercises today.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class MerchantCategoryRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchant_category_rules"
    __table_args__ = (
        # The core identity of a rule - see the module docstring. This is
        # the actual backstop against a concurrent duplicate create, not
        # the service-layer pre-check (see app.services.merchant_rule_service),
        # same convention as uq_categories_user_name_active.
        UniqueConstraint(
            "user_id", "merchant_key", name="uq_merchant_category_rules_user_merchant"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merchant_key: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
