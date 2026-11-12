"""Linked-account/sync-run request/response schemas, used by
app.api.v1.sync.

Every request schema is `extra="forbid"`, same convention as every other
schema in this app - and deliberately carries NOTHING that could resemble a
payment credential: no PIN, CVV, OTP, password, or payment-authorization
field of any kind, ever. `LinkedAccountUpdate` in particular only ever
accepts the one field app.services.sync_service actually supports mutating
(`account_id`) - a client can never touch consent_id, provider identifiers,
sync statistics, ownership, or consent_status through it.

Every response schema is equally deliberate about what it leaves OUT: no
provider consent secret, no full raw provider payload, no masked-account
value beyond what app.models.linked_account itself ever stores (already
masked at the source).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.linked_account import SyncConsentStatus
from app.models.sync_run import SyncRunStatus


class LinkInitiateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A free-text hint only (e.g. "HDFC Bank") - never a credential, and
    # the mock provider does not even use it today; see
    # app.sync.provider.base.BankSyncProvider.initiate_link.
    institution_hint: str | None = Field(default=None, max_length=200)


class LinkInitiationRead(BaseModel):
    """`consent_handle` is an opaque, short-lived token the client must
    pass back to the callback endpoint - never a credential or a secret
    the provider could use to move money; see
    app.sync.provider.base.LinkInitiation."""

    model_config = ConfigDict(from_attributes=True)

    provider: str
    consent_handle: str
    redirect_url: str
    expires_at: datetime


class LinkedAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID


class LinkedAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    provider: str
    external_institution_name: str
    fip_reference: str | None
    consent_status: SyncConsentStatus
    consent_expires_at: datetime | None
    masked_account_ref: str | None
    last_synced_at: datetime | None
    last_sync_status: str | None
    created_at: datetime
    updated_at: datetime


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    linked_account_id: UUID
    started_at: datetime
    completed_at: datetime | None
    status: SyncRunStatus
    transactions_fetched: int
    transactions_created: int
    transactions_skipped_duplicate: int
    error_message: str | None
