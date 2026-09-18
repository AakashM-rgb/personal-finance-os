"""Linked-account/sync-run response schemas.

There is deliberately no *Create/*Update request schema here yet - Phase B
has no API layer, and app.services.sync_service's link-lifecycle functions
take plain typed arguments instead. These Read schemas exist now so a later
phase's API can return exactly this shape without a schema change of its
own.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.linked_account import SyncConsentStatus
from app.models.sync_run import SyncRunStatus


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
