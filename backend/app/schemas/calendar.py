"""Financial calendar request/response schemas.

Every figure is computed from the authenticated caller's own real
transaction and recurring-transaction data - nothing is fabricated. A
`CalendarBill` is a SCHEDULED, not-yet-generated occurrence (see
app.services.calendar_calculations) - it is never counted in a day's
income_minor/expense_minor, and it is distinct from the real,
already-occurred rows in `transactions` (which include transfers, even
though transfers never count toward income_minor/expense_minor either -
see app.services.calendar_service).
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.models.recurring_transaction import RecurrenceFrequency
from app.models.transaction import TransactionType
from app.schemas.transaction import TransactionRead


class CalendarBill(BaseModel):
    recurring_transaction_id: UUID
    name: str
    type: TransactionType
    amount_minor: int
    currency: str
    frequency: RecurrenceFrequency
    is_subscription: bool


class CalendarDay(BaseModel):
    date: date
    income_minor: int
    expense_minor: int
    net_minor: int
    # Real, already-occurred transactions on this day - includes
    # transfers (visible, but excluded from income_minor/expense_minor).
    transactions: list[TransactionRead]
    # Scheduled but not-yet-generated occurrences due on this day.
    bills: list[CalendarBill]


class CalendarMonth(BaseModel):
    year: int
    month: int
    currency: str
    days: list[CalendarDay]
