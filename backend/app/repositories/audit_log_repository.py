"""Data access for audit_logs beyond the single insert in app.services.audit_service."""

import uuid

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditLogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def anonymize_for_user(self, user_id: uuid.UUID) -> None:
        """Strips what identifies or describes the person - IP address, user
        agent, and metadata such as balances - from every audit row of
        `user_id`, keeping each row's action and time. The audit trail is
        meant to outlive a deleted user (audit_logs.user_id is SET NULL);
        their personal data is not."""
        await self._db.execute(
            update(AuditLog)
            .where(AuditLog.user_id == user_id)
            .values(ip_address=None, user_agent=None, metadata_json=None)
        )
