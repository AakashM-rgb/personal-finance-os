"""Linked account model - a user's consent-based link to an external
financial institution account, via a sync provider (see app.sync.provider).

This is deliberately a separate, 1:many table rather than fields bolted onto
`User`/`UserSettings`, since a user may link several institution accounts.
`account_id` is nullable and only ever set once the user explicitly maps this
link to one of their own internal `Account` rows (mirrors the Receipt
scan-first pattern in app.models.receipt: the external link can exist before
it's connected to anything in the ledger). `ondelete="SET NULL"` on
`account_id` means deleting the internal account never deletes the link
itself or its consent/audit history.

`masked_account_ref` only ever holds a masked reference (e.g. "XX1234"),
never a full account number - see CLAUDE.md §12 data-minimization rules.
Nothing on this model can ever represent a PIN, password, OTP, or payment
authorization credential; a provider only ever hands back an opaque
`consent_id` it manages on its own side (see app.sync.provider.base).

This model carries no read/write methods of its own - all sync
orchestration logic belongs in app.services.sync_service, never here.

`external_account_id` is the provider-defined identifier for this specific
institution account under the consent (see
app.sync.provider.base.LinkedInstitutionAccount) - required so a later
sync can ask the provider for this exact account's transactions without
re-listing every account under the consent each time. The unique
constraint on (consent_id, external_account_id) makes completing the same
consent handle twice (a retried callback, a double form submit) safely
idempotent at the database level, mirroring how Transaction's own
idempotency_key constraint backstops create_transaction.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class SyncConsentStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    EXPIRED = "expired"


class LinkedAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "linked_accounts"
    __table_args__ = (
        UniqueConstraint(
            "consent_id", "external_account_id", name="uq_linked_accounts_consent_external_account"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Mapped internal ledger account, once the user connects this link to
    # one - see the module docstring.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Which BankSyncProvider implementation this link was created through
    # (e.g. "mock") - never a specific bank, which is institution-level
    # metadata below.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    external_institution_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Opaque, provider-defined identifier for this specific institution
    # account under the consent - see the module docstring.
    external_account_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # The Financial Information Provider reference an Account Aggregator
    # flow would identify the bank by - opaque and provider-defined; never
    # assumed to have a particular shape here.
    fip_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Opaque consent handle managed by the provider/AA - never a credential.
    consent_id: Mapped[str] = mapped_column(String(200), nullable=False)
    consent_status: Mapped[SyncConsentStatus] = mapped_column(
        str_enum_column(SyncConsentStatus, name="sync_consent_status"),
        nullable=False,
        default=SyncConsentStatus.PENDING,
    )
    consent_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Masked only (e.g. "XX1234") - never a full account number.
    masked_account_ref: Mapped[str | None] = mapped_column(String(50), nullable=True)

    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
