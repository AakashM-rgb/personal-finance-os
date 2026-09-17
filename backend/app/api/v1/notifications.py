"""Notification endpoints. Every route is authenticated and scoped to the
caller's own notifications via app.services.notification_service - a
notification id alone is never enough to read or mark-read one; ownership
is re-checked on every single call.

`list_notifications` and `get_unread_count` both call
notification_service.generate_due_for_user first - the same "regenerate,
then read" pattern app.api.v1.recurring_transactions could use but
doesn't (recurring generation is a deliberate, explicit user action there);
here it keeps notification data always fresh without requiring the
frontend to separately remember to trigger generation, and is safe to run
on every call because generation is fully idempotent (see
app.models.notification's docstring)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

_MAX_PAGE_SIZE = 100


@router.get("", response_model=None)
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(default=20, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    user_id = current_user.id
    await notification_service.generate_due_for_user(db, user_id=user_id)
    await db.commit()
    notifications, total = await notification_service.list_notifications(
        db, user_id=user_id, unread_only=unread_only, limit=limit, offset=offset
    )
    meta = {"count": len(notifications), "total": total}
    return {"data": notifications, "error": None, "meta": meta}


@router.get("/unread-count", response_model=None)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    user_id = current_user.id
    await notification_service.generate_due_for_user(db, user_id=user_id)
    await db.commit()
    count = await notification_service.get_unread_count(db, user_id=user_id)
    return {"data": {"unread_count": count}, "error": None, "meta": None}


@router.put("/{notification_id}/read", response_model=None)
async def mark_notification_read(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    notification = await notification_service.mark_notification_read(
        db, user_id=current_user.id, notification_id=notification_id
    )
    await db.commit()
    return {"data": notification, "error": None, "meta": None}


@router.post("/read-all", response_model=None)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    updated_count = await notification_service.mark_all_read(db, user_id=current_user.id)
    await db.commit()
    return {"data": {"updated_count": updated_count}, "error": None, "meta": None}
