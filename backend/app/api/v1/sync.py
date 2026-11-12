"""Automatic transaction sync endpoints. Every route is authenticated and
scoped to the caller's own linked accounts/sync runs via
app.services.sync_service - a linked_account_id alone is never enough to
read, update, sync, or revoke one; ownership is re-checked on every call
(see app.services.sync_service._get_owned_linked_account).

The callback route's `{consent_handle}` is deliberately NOT a
LinkedAccount id - no LinkedAccount row exists until the provider consent
actually completes (see app.services.sync_service.complete_link), so the
one opaque, short-lived token the client got back from POST /sync/links is
what identifies this specific in-flight consent flow. Every other route
below (`{linked_account_id}`) operates on a real, already-persisted
LinkedAccount row.

Nothing here can ever initiate a payment, transfer, or withdrawal, or
accept a PIN/OTP/CVV/password - the service layer this router calls is
built on a permanently read-only provider Protocol (see
app.sync.provider.base.BankSyncProvider).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.sync import LinkedAccountUpdate, LinkInitiateRequest, LinkInitiationRead
from app.services import sync_service

router = APIRouter(prefix="/sync", tags=["sync"])
settings = get_settings()


def _client_context(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


@router.post("/links", response_model=None, status_code=201)
@limiter.limit(settings.sync_link_rate_limit)
async def initiate_link(
    request: Request,
    body: LinkInitiateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ip_address, user_agent = _client_context(request)
    initiation = await sync_service.initiate_link(
        db,
        user_id=current_user.id,
        institution_hint=body.institution_hint,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return {"data": LinkInitiationRead.model_validate(initiation), "error": None, "meta": None}


@router.get("/links", response_model=None)
async def list_linked_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    linked_accounts = await sync_service.list_linked_accounts(db, user_id=current_user.id)
    return {"data": linked_accounts, "error": None, "meta": {"count": len(linked_accounts)}}


@router.get("/links/{linked_account_id}", response_model=None)
async def get_linked_account(
    linked_account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    linked_account = await sync_service.get_linked_account(
        db, user_id=current_user.id, linked_account_id=linked_account_id
    )
    return {"data": linked_account, "error": None, "meta": None}


@router.post("/links/{consent_handle}/callback", response_model=None, status_code=201)
async def complete_link(
    consent_handle: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ip_address, user_agent = _client_context(request)
    linked_accounts = await sync_service.complete_link(
        db,
        user_id=current_user.id,
        consent_handle=consent_handle,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return {"data": linked_accounts, "error": None, "meta": {"count": len(linked_accounts)}}


@router.patch("/links/{linked_account_id}", response_model=None)
async def update_linked_account(
    linked_account_id: UUID,
    body: LinkedAccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    linked_account = await sync_service.update_linked_account_mapping(
        db,
        user_id=current_user.id,
        linked_account_id=linked_account_id,
        account_id=body.account_id,
    )
    await db.commit()
    return {"data": linked_account, "error": None, "meta": None}


@router.delete("/links/{linked_account_id}", response_model=None, status_code=200)
async def revoke_link(
    linked_account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ip_address, user_agent = _client_context(request)
    linked_account = await sync_service.revoke_link(
        db,
        user_id=current_user.id,
        linked_account_id=linked_account_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return {"data": linked_account, "error": None, "meta": None}


@router.post("/links/{linked_account_id}/sync", response_model=None)
@limiter.limit(settings.sync_trigger_rate_limit)
async def trigger_sync(
    linked_account_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    ip_address, user_agent = _client_context(request)
    sync_run = await sync_service.trigger_sync(
        db,
        user_id=current_user.id,
        linked_account_id=linked_account_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    return {"data": sync_run, "error": None, "meta": None}


@router.get("/links/{linked_account_id}/runs", response_model=None)
async def list_sync_runs(
    linked_account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    sync_runs = await sync_service.list_sync_runs(
        db, user_id=current_user.id, linked_account_id=linked_account_id
    )
    return {"data": sync_runs, "error": None, "meta": {"count": len(sync_runs)}}
