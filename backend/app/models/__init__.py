"""Import every model so they register on the shared declarative registry
before Alembic autogenerate or SQLAlchemy mapper configuration runs."""

from app.models.account import Account, AccountType
from app.models.audit_log import AuditLog
from app.models.category import Category
from app.models.credit_card_details import CreditCardDetails
from app.models.session import Session
from app.models.user import User
from app.models.user_settings import UserSettings

__all__ = [
    "Account",
    "AccountType",
    "AuditLog",
    "Category",
    "CreditCardDetails",
    "Session",
    "User",
    "UserSettings",
]
