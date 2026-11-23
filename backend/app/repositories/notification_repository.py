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
        """Inserts a new notification, or returns None if one with this exact
        (user_id, dedupe_key) already exists. There is no pre-check SELECT:
        the database's own unique constraint
        (uq_notifications_user_dedupe_key) is the only thing deciding, so a
        concurrent caller racing to create the same notification is a no-op
        here, never a raw 500.

        The insert runs inside a SAVEPOINT because the duplicate case is the
        *normal* one, not a rare race: dedupe keys deterministically encode
        real-world events, so every regeneration run re-attempts the
        notifications it already created. Rolling back the whole transaction
        here (as this once did) discarded every notification the earlier
        detectors in the same request had just created - they were silently
        lost, and the caller could not tell, because a duplicate and a
        wiped-out batch both return None. A savepoint undoes only the one
        failed insert."""
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
        try:
            # `add` belongs inside the savepoint: rolling back to the
            # savepoint undoes it, so the outer flush cannot re-attempt the
            # insert that just failed.
            async with self._db.begin_nested():
                self._db.add(notification)
                await self._db.flush()
        except IntegrityError:
            return None
        return notification
