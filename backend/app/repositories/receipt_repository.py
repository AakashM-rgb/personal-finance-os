"""Data access for receipts. Every query is scoped to a user_id so a
caller can never read, update, or delete another user's receipt by
guessing an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt


class ReceiptRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[Receipt]:
        stmt = (
            select(Receipt)
            .where(Receipt.user_id == user_id)
            .order_by(Receipt.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(self, receipt_id: uuid.UUID, user_id: uuid.UUID) -> Receipt | None:
        stmt = select(Receipt).where(Receipt.id == receipt_id, Receipt.user_id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_storage_key(self, storage_key: str) -> Receipt | None:
        """Used only to guarantee a freshly generated key doesn't already
        exist before the very first save - not an access path (callers
        must still go through get_by_id_for_user for anything user-facing)."""
        stmt = select(Receipt).where(Receipt.storage_key == storage_key)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, receipt: Receipt) -> None:
        self._db.add(receipt)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, receipt: Receipt) -> None:
        await self._db.delete(receipt)
