"""The recurring-transaction generation job (see app.jobs for the
abstraction this fits into). `run_for_user` is what the manual "generate
now" API route calls; `run_for_all_users` is the system-wide sweep a real
scheduler would call on a fixed interval instead - it is not wired to any
user-facing endpoint, since it operates across every user's data at once.
Both simply delegate to app.services.recurring_transaction_service, which
holds the actual generation logic - this module is only the seam.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.transaction import TransactionRead
from app.services import recurring_transaction_service


async def run_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[TransactionRead]:
    return await recurring_transaction_service.generate_due_for_user(db, user_id=user_id)


async def run_for_all_users(db: AsyncSession) -> list[TransactionRead]:
    return await recurring_transaction_service.generate_due_for_all_users(db)
