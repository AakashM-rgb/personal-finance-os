"""The notification generation job (see app.jobs for the abstraction this
fits into). `run_for_user` is what the notification-listing endpoints
call inline (see app.api.v1.notifications); `run_for_all_users` is the
system-wide sweep a real scheduler would call on a fixed interval instead
- it is not wired to any user-facing endpoint, since it operates across
every user's data at once. Both simply delegate to
app.services.notification_service, which holds the actual generation
logic - this module is only the seam (identical shape to
app.jobs.recurring_transaction_generator)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import notification_service


async def run_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    await notification_service.generate_due_for_user(db, user_id=user_id)


async def run_for_all_users(db: AsyncSession) -> None:
    await notification_service.generate_due_for_all_users(db)
