"""Handling of server-to-server notifications from Setu Account Aggregator
(see app.api.v1.setu_notifications).

Today this only records a structured, credential-free log line per
notification - it deliberately persists nothing and mutates no
LinkedAccount. Two reasons, both of which must be resolved before this
module may change ledger or consent state:

- Setu documents no signature/authenticity mechanism for these
  notifications (SYNC_PROVIDER_DECISION.md, row 2), so the request is
  unauthenticated. Acting on it would let anyone who guesses a consent id
  forge a consent ACTIVE/REVOKED transition for another user.
- No persistence location fits yet: SyncConsentStatus has no REJECTED
  value, nothing stores a data-session id, and no Setu-backed LinkedAccount
  can exist while app.sync.provider.setu_sandbox is a stub.

Once verification exists, `handle_notification` is the seam: it should
resolve the LinkedAccount(s) by consent_id and delegate the state change to
app.services.sync_service - never write LinkedAccount rows itself.

Logged fields are opaque resource identifiers, statuses, and Setu's error
code only. Setu's free-text error message and any nested account/FIP data
are never logged (the schema already drops the latter at the boundary).
"""

import logging

from app.schemas.setu_notification import SetuNotification

logger = logging.getLogger("app.sync.setu_notifications")


async def handle_notification(notification: SetuNotification) -> None:
    status = notification.consent_status or notification.data_session_status
    log = logger.info if notification.success else logger.warning
    log(
        "setu_notification_received",
        extra={
            "notification_type": notification.type.value,
            "notification_id": notification.notification_id,
            "consent_id": notification.consent_id,
            "data_session_id": notification.data_session_id,
            "status": status.value if status else None,
            "success": notification.success,
            "error_code": notification.error.code if notification.error else None,
            "notification_timestamp": notification.timestamp.isoformat(),
        },
    )
