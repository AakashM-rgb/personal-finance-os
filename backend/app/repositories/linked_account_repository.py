"""Data access for linked accounts. Every query is scoped to a user_id so a
caller can never read or mutate another user's linked account by guessing
an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.linked_account import LinkedAccount


class LinkedAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[LinkedAccount]:
        stmt = (
            select(LinkedAccount)
            .where(LinkedAccount.user_id == user_id)
            .order_by(LinkedAccount.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self, linked_account_id: uuid.UUID, user_id: uuid.UUID
    ) -> LinkedAccount | None:
        stmt = select(LinkedAccount).where(
            LinkedAccount.id == linked_account_id, LinkedAccount.user_id == user_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_consent_and_external_account(
        self, *, consent_id: str, external_account_id: str
    ) -> LinkedAccount | None:
        """Used only to make completing the same consent handle twice (a
        retried callback, a double form submit) idempotent - the database's
        own unique constraint (see app.models.linked_account) is what
        actually prevents the duplicate row; this just turns the resulting
        race into a clean "return the existing link" instead of a raw
        IntegrityError reaching the caller."""
        stmt = select(LinkedAccount).where(
            LinkedAccount.consent_id == consent_id,
            LinkedAccount.external_account_id == external_account_id,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, linked_account: LinkedAccount) -> None:
        self._db.add(linked_account)

    async def flush(self) -> None:
        await self._db.flush()
