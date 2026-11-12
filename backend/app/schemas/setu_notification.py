"""Setu Account Aggregator notification (webhook) payload schema, used by
app.api.v1.setu_notifications.

Unlike every other request schema in this app, these models IGNORE unknown
fields instead of forbidding them: the sender is Setu, not our own client,
and a new upstream field must never make Setu's notification fail. Ignoring
is also deliberate data minimization - only the fields declared here are
ever parsed; nested account/FIP details Setu may include under `data` (e.g.
masked account numbers) are dropped at the boundary and never reach the
service layer or a log line.

Every identifier that the service layer logs is constrained to a short,
printable character set, since this endpoint is unauthenticated and any
string it accepts ends up in application logs (log-injection guard).
"""

import enum
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9._:-]+$"

SetuIdentifier = Annotated[str, Field(min_length=1, max_length=200, pattern=_IDENTIFIER_PATTERN)]


class SetuNotificationType(enum.StrEnum):
    CONSENT_STATUS_UPDATE = "CONSENT_STATUS_UPDATE"
    SESSION_STATUS_UPDATE = "SESSION_STATUS_UPDATE"


class SetuConsentStatus(enum.StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"


class SetuDataSessionStatus(enum.StrEnum):
    PENDING = "PENDING"
    PARTIAL = "PARTIAL"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class SetuNotificationData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = Field(min_length=1, max_length=50)


class SetuNotificationError(BaseModel):
    """`message` is accepted but never logged - it is free text from an
    unauthenticated request and may carry anything."""

    model_config = ConfigDict(extra="ignore")

    code: str = Field(min_length=1, max_length=100, pattern=_IDENTIFIER_PATTERN)
    message: str | None = Field(default=None, max_length=1000)


class SetuNotification(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: SetuNotificationType
    consent_id: SetuIdentifier = Field(alias="consentId")
    timestamp: datetime
    success: bool
    # Absent/null only on a failed notification - see _check_status.
    data: SetuNotificationData | None = None
    error: SetuNotificationError | None = None
    notification_id: SetuIdentifier | None = Field(default=None, alias="notificationId")
    data_session_id: SetuIdentifier | None = Field(default=None, alias="dataSessionId")

    @model_validator(mode="after")
    def _check_status(self) -> "SetuNotification":
        if self.type is SetuNotificationType.SESSION_STATUS_UPDATE and self.data_session_id is None:
            raise ValueError(f"dataSessionId is required for {self.type}.")
        if self.data is None:
            if self.success:
                raise ValueError("data is required when success is true.")
            return self
        allowed = (
            SetuConsentStatus
            if self.type is SetuNotificationType.CONSENT_STATUS_UPDATE
            else SetuDataSessionStatus
        )
        if self.data.status not in allowed.__members__:
            raise ValueError(f"Unsupported status for {self.type}.")
        return self

    @property
    def consent_status(self) -> SetuConsentStatus | None:
        if self.type is not SetuNotificationType.CONSENT_STATUS_UPDATE or self.data is None:
            return None
        return SetuConsentStatus(self.data.status)

    @property
    def data_session_status(self) -> SetuDataSessionStatus | None:
        if self.type is not SetuNotificationType.SESSION_STATUS_UPDATE or self.data is None:
            return None
        return SetuDataSessionStatus(self.data.status)
