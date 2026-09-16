"""Receipt model.

A receipt can exist before any transaction does (scan-first flow, per
CLAUDE.md §4) - `transaction_id` is nullable and only ever set once the
user explicitly asks to create/attach a transaction from a CONFIRMED
receipt (see app.services.receipt_service.create_transaction_from_receipt).
Deleting that transaction later must never delete the receipt itself
(the scanned evidence should outlive it), hence `ondelete="SET NULL"`.

The `extracted_*` and `confirmed_*` columns are deliberately separate,
never the same column: `extracted_*` holds whatever the OCR provider
produced (a candidate, possibly wrong, possibly empty) and is written
once by the OCR step; `confirmed_*` holds only what the user explicitly
submitted through the review/confirm endpoint and is the sole source used
if a transaction is ever created from this receipt. Nothing ever copies
`extracted_*` into `confirmed_*` automatically.

Items are stored as JSONB - a small, receipt-scoped list of
{description, quantity, unit_price_minor, line_total_minor} objects.
`quantity` is a plain string (e.g. "2", "1.5kg"), never a float, since it
is display metadata, not itself a financial calculation input; every
money field in the JSON is an integer minor-unit amount, like everywhere
else in this application.
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class ReceiptStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class Receipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "receipts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[ReceiptStatus] = mapped_column(
        str_enum_column(ReceiptStatus, name="receipt_status"),
        nullable=False,
        default=ReceiptStatus.PENDING,
    )

    ocr_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ocr_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ocr_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    extracted_merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    extracted_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    extracted_total_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    extracted_tax_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    extracted_items: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    suggested_category_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )

    confirmed_merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    confirmed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_total_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_tax_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    confirmed_items: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
