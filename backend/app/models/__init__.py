"""Import every model so they register on the shared declarative registry
before Alembic autogenerate or SQLAlchemy mapper configuration runs."""

from app.models.account import Account, AccountType
from app.models.audit_log import AuditLog
from app.models.budget import Budget, BudgetItem
from app.models.category import Category
from app.models.credit_card_details import CreditCardDetails
from app.models.linked_account import LinkedAccount, SyncConsentStatus
from app.models.notification import Notification, NotificationCategory
from app.models.receipt import Receipt, ReceiptStatus
from app.models.recurring_transaction import RecurrenceFrequency, RecurringTransaction
from app.models.savings_goal import SavingsGoal
from app.models.session import Session
from app.models.subscription import Subscription
from app.models.sync_run import SyncRun, SyncRunStatus
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.models.user_settings import UserSettings

__all__ = [
    "Account",
    "AccountType",
    "AuditLog",
    "Budget",
    "BudgetItem",
    "Category",
    "CreditCardDetails",
    "LinkedAccount",
    "Notification",
    "NotificationCategory",
    "Receipt",
    "ReceiptStatus",
    "RecurrenceFrequency",
    "RecurringTransaction",
    "SavingsGoal",
    "Session",
    "Subscription",
    "SyncConsentStatus",
    "SyncRun",
    "SyncRunStatus",
    "Transaction",
    "TransactionType",
    "User",
    "UserSettings",
]
