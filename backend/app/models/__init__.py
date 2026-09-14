"""Import every model so they register on the shared declarative registry
before Alembic autogenerate or SQLAlchemy mapper configuration runs."""

from app.models.audit_log import AuditLog
from app.models.session import Session
from app.models.user import User
from app.models.user_settings import UserSettings

__all__ = ["AuditLog", "Session", "User", "UserSettings"]
