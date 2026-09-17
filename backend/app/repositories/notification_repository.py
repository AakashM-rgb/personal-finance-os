"""Data access for notifications. Every query is scoped to a user_id so a
caller can never read, count, or mark-read another user's notification by
guessing an id."""

import uuid
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationCategory

_MAX_PAGE_SIZE = 100


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(
        self, user_id: uuid.UUID, *, unread_only: bool, limit: int, offset: int
    ) -> tuple[list[Notification], int]:
        limit = min(limit, _MAX_PAGE_SIZE)
        conditions = [Notification.user_id == user_id]
        if unread_only:
            conditions.append(Notification.is_read.is_(False))

        count_stmt = select(func.count()).select_from(Notification).where(*conditions)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(Notification)
            .where(*conditions)
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def count_unread_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        return (await self._db.execute(stmt)).scalar_one()

    async def get_by_id_for_user(
        self, notification_id: uuid.UUID, user_id: uuid.UUID
    ) -> Notification | None:
        stmt = select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_read(self, notification: Notification) -> None:
        notification.is_read = True
        await self._db.flush()

    async def mark_all_read_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True)
        )
        result = await self._db.execute(stmt)
        return cast(CursorResult, result).rowcount or 0

    async def create_if_not_exists(
        self,
        *,
        user_id: uuid.UUID,
        category: NotificationCategory,
        title: str,
        message: str,
        dedupe_key: str,
        reference_type: str | None = None,
        reference_id: str | None = None,
        action_url: str | None = None,
    ) -> Notification | None:
        """Inserts a new notification, or returns None if one with this
        exact (user_id, dedupe_key) already exists - the real backstop is
        the database's own unique constraint (uq_notifications_user_dedupe_key),
        not this pre-check; a concurrent caller racing to create the same
        notification hits that constraint and is treated as a no-op here,
        never a raw 500 (same recovery pattern as
        app.services.transaction_service.create_transaction's own
        idempotency-key race)."""
        notification = Notification(
            user_id=user_id,
            category=category,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
            reference_type=reference_type,
            reference_id=reference_id,
            action_url=action_url,
        )
        self._db.add(notification)
        try:
            await self._db.flush()
        except IntegrityError:
            await self._db.rollback()
            return None
        return notification
