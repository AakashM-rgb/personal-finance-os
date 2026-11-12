"""Setu Account Aggregator notification webhook - a server-to-server entry
point called by Setu, never by our own frontend.

Deliberately unauthenticated (no get_current_user / user JWT): Setu has no
user session with this app. It is NOT the authenticated in-app consent
callback (POST /sync/links/{consent_handle}/callback in app.api.v1.sync).
Because the caller cannot be verified yet, the service it delegates to
only logs and never changes state - see
app.services.setu_notification_service.

Setu's failure notifications (`success: false`) are still acknowledged
with 200: the delivery itself succeeded, and a non-2xx would only trigger
pointless redelivery. Malformed or unsupported payloads get the standard
422 validation envelope.
"""

from fastapi import APIRouter, Request

from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.setu_notification import SetuNotification
from app.services import setu_notification_service

router = APIRouter(prefix="/setu", tags=["setu"])
settings = get_settings()


@router.post("/notifications", response_model=None)
@limiter.limit(settings.setu_notification_rate_limit)
async def receive_notification(request: Request, body: SetuNotification) -> dict:
    await setu_notification_service.handle_notification(body)
    return {"data": {"received": True}, "error": None, "meta": None}
