"""Data access for the per-account login throttle's failure records.

Not user-scoped like the other repositories: rows are keyed by an opaque
account key (an HMAC of the submitted email), never by user_id - see
app.models.login_failure for why.
"""

from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.login_failure import LoginFailure


class LoginFailureRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def try_lock_account(self, lock_id: int) -> bool:
        """Takes the account's lock until the transaction ends, across every
        worker and instance sharing the database, so concurrent attempts can't
        all pass the count check before any of them records its failure.
        Never waits: a queue of blocked attempts would each hold a pooled
        connection, letting a flood against one email starve every user."""
        result = await self._db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id}
        )
        return bool(result.scalar_one())

    async def count_since(self, account_key: str, since: datetime) -> int:
        result = await self._db.execute(
            select(func.count())
            .select_from(LoginFailure)
            .where(LoginFailure.account_key == account_key, LoginFailure.created_at > since)
        )
        return result.scalar_one()

    async def add(self, account_key: str) -> None:
        self._db.add(LoginFailure(account_key=account_key))
        await self._db.flush()

    async def delete_for_account(self, account_key: str) -> None:
        await self._db.execute(delete(LoginFailure).where(LoginFailure.account_key == account_key))

    async def delete_older_than(self, cutoff: datetime) -> None:
        await self._db.execute(delete(LoginFailure).where(LoginFailure.created_at <= cutoff))
