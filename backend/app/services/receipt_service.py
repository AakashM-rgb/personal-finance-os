"""Receipt business logic: upload validation, private storage, OCR
extraction, the human review/confirm workflow, and (only after explicit
confirmation) creating a real transaction from a receipt.

OCR output is NEVER authoritative. `extracted_*` columns hold whatever the
OCR provider found (see app.models.receipt); `confirmed_*` columns hold
only what the user explicitly submitted through confirm_receipt, and
nothing here ever copies one into the other automatically. Only
confirmed_* is ever used to create a transaction.
"""

import re
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, time
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.models.category import Category
from app.models.receipt import Receipt, ReceiptStatus
from app.models.transaction import TransactionType
from app.ocr.factory import get_ocr_provider
from app.repositories.category_repository import CategoryRepository
from app.repositories.receipt_repository import ReceiptRepository
from app.schemas.receipt import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_EXTENSIONS,
    RECEIPT_MAX_FILE_SIZE_BYTES,
    ReceiptConfirmRequest,
    ReceiptExtraction,
    ReceiptItemData,
    ReceiptRead,
)
from app.schemas.transaction import TransactionCreate, TransactionRead
from app.services import category_service, transaction_service
from app.services.keyword_categorization import suggest_category_name
from app.storage.base import generate_storage_key
from app.storage.factory import get_storage_provider

_EXTENSION_TO_CONTENT_TYPE = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "pdf": "application/pdf",
}
_CONTENT_TYPE_TO_EXTENSION = {"image/jpeg": "jpg", "image/png": "png", "application/pdf": "pdf"}

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_PDF_MAGIC = b"%PDF-"

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
_MAX_FILENAME_LENGTH = 255


def _sniff_content_type(content: bytes) -> str | None:
    """Determines the file's real type from its own magic bytes -
    never from the client-supplied filename or declared content type."""
    if content.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if content.startswith(_PDF_MAGIC):
        return "application/pdf"
    return None


def sanitize_filename(filename: str | None) -> str | None:
    """Returns a display-only name - the last path segment, control
    characters stripped, length-capped. This value is NEVER used to build
    a filesystem path (see app.storage.base.generate_storage_key, which
    never reads it at all)."""
    if not filename:
        return None
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    name = _CONTROL_CHARS_RE.sub("", name).strip()
    if not name or name in {".", ".."}:
        return None
    return name[:_MAX_FILENAME_LENGTH]


def content_disposition_value(filename: str | None, *, disposition: str = "inline") -> str:
    """Builds a safe `Content-Disposition` header value for a stored
    filename that, while control-character-free (see sanitize_filename),
    is still otherwise arbitrary user input - it can contain `"` or `\\`,
    which would otherwise break out of the quoted `filename="..."`
    parameter. Both the quoted-string fallback (quotes/backslashes
    escaped, non-ASCII stripped, per RFC 6266 the ASCII fallback) and an
    RFC 5987 percent-encoded `filename*` parameter (full Unicode fidelity)
    are included, exactly as recommended by RFC 6266 §5."""
    if not filename:
        return disposition

    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "receipt"
    escaped = ascii_fallback.replace("\\", "\\\\").replace('"', '\\"')
    encoded = quote(filename, safe="")
    return f'{disposition}; filename="{escaped}"; filename*=UTF-8\'\'{encoded}'


def _validate_pdf_readable(content: bytes) -> None:
    import io

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(content))
        _ = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, IndexError) as exc:
        raise ValidationAppError(
            "The uploaded PDF appears to be corrupt or unreadable.",
            field_errors={"file": "invalid_content"},
        ) from exc


def _validate_upload(
    *, filename: str | None, declared_content_type: str | None, content: bytes
) -> str:
    """Returns the TRUSTED content type, derived from the file's actual
    bytes. Raises ValidationAppError for anything empty, oversized,
    unsupported, or whose real content doesn't match what was claimed."""
    if not content:
        raise ValidationAppError("The uploaded file is empty.", field_errors={"file": "empty"})
    if len(content) > RECEIPT_MAX_FILE_SIZE_BYTES:
        raise ValidationAppError(
            f"Files must be {RECEIPT_MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB or smaller.",
            field_errors={"file": "too_large"},
        )

    sanitized_name = sanitize_filename(filename)
    extension = (
        sanitized_name.rsplit(".", 1)[-1].lower()
        if sanitized_name and "." in sanitized_name
        else None
    )
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationAppError(
            "Unsupported file type. Upload a JPG, PNG, or PDF.",
            field_errors={"file": "unsupported_type"},
        )

    if declared_content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationAppError(
            "Unsupported file type. Upload a JPG, PNG, or PDF.",
            field_errors={"file": "unsupported_type"},
        )

    sniffed_type = _sniff_content_type(content)
    if sniffed_type is None or sniffed_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationAppError(
            "The file's contents don't look like a valid JPG, PNG, or PDF.",
            field_errors={"file": "invalid_content"},
        )

    if sniffed_type != _EXTENSION_TO_CONTENT_TYPE[extension]:
        raise ValidationAppError(
            "The file's contents don't match its extension.",
            field_errors={"file": "content_mismatch"},
        )

    if sniffed_type == "application/pdf":
        _validate_pdf_readable(content)

    return sniffed_type


async def _categories_by_id(db: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, Category]:
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    return {c.id: c for c in categories}


def _items_from_json(raw: list[dict] | None) -> list[ReceiptItemData]:
    return [ReceiptItemData(**item) for item in (raw or [])]


def _build_read(receipt: Receipt, categories_by_id: dict[uuid.UUID, Category]) -> ReceiptRead:
    category = categories_by_id.get(receipt.category_id) if receipt.category_id else None
    suggested_category = (
        categories_by_id.get(receipt.suggested_category_id)
        if receipt.suggested_category_id
        else None
    )

    extraction = None
    if receipt.status != ReceiptStatus.PENDING:
        extraction = ReceiptExtraction(
            provider=receipt.ocr_provider,
            confidence=receipt.ocr_confidence,
            processed_at=receipt.ocr_processed_at,
            error=receipt.ocr_error,
            merchant=receipt.extracted_merchant,
            date=receipt.extracted_date,
            total_minor=receipt.extracted_total_minor,
            tax_minor=receipt.extracted_tax_minor,
            items=_items_from_json(receipt.extracted_items),
            suggested_category_id=receipt.suggested_category_id,
            suggested_category_name=suggested_category.name if suggested_category else None,
        )

    return ReceiptRead(
        id=receipt.id,
        transaction_id=receipt.transaction_id,
        original_filename=receipt.original_filename,
        content_type=receipt.content_type,
        file_size_bytes=receipt.file_size_bytes,
        status=receipt.status.value,
        extraction=extraction,
        confirmed_merchant=receipt.confirmed_merchant,
        confirmed_date=receipt.confirmed_date,
        confirmed_total_minor=receipt.confirmed_total_minor,
        confirmed_tax_minor=receipt.confirmed_tax_minor,
        confirmed_items=_items_from_json(receipt.confirmed_items),
        category_id=receipt.category_id,
        category_name=category_service.display_name(category) if category else None,
        category_icon=category_service.display_icon(category) if category else None,
        category_color=category_service.display_color(category) if category else None,
        confirmed_at=receipt.confirmed_at,
        created_at=receipt.created_at,
        updated_at=receipt.updated_at,
    )


async def _run_ocr(db: AsyncSession, receipt: Receipt, *, content: bytes) -> None:
    """Synchronous today, called inline from upload_receipt right after the
    file is stored (Part 11: made explicit, and safe - any failure here
    leaves the receipt in a usable FAILED state, never half-written or
    crashing the upload). Deliberately isolated with no request/response
    coupling, so it can be moved behind app.jobs later without this
    function's body changing at all."""
    provider = get_ocr_provider()

    try:
        result = await provider.extract(file_bytes=content, content_type=receipt.content_type)
    except Exception as exc:  # noqa: BLE001 - a provider failure must never crash the upload
        receipt.status = ReceiptStatus.FAILED
        receipt.ocr_error = f"OCR processing failed: {exc}"
        return

    if result.error:
        receipt.status = ReceiptStatus.FAILED
        receipt.ocr_provider = result.provider
        receipt.ocr_error = result.error
        return

    receipt.status = ReceiptStatus.PROCESSED
    receipt.ocr_provider = result.provider
    receipt.ocr_confidence = result.confidence
    receipt.ocr_processed_at = datetime.now(UTC)
    receipt.extracted_merchant = result.merchant
    receipt.extracted_date = result.occurred_on
    receipt.extracted_total_minor = result.total_minor
    receipt.extracted_tax_minor = result.tax_minor
    receipt.extracted_items = [asdict(item) for item in result.items]

    categories = await CategoryRepository(db).list_visible_for_user(
        receipt.user_id, include_inactive=False
    )
    suggested_name = suggest_category_name(
        merchant=result.merchant,
        item_descriptions=[item.description for item in result.items],
        category_names=[c.name for c in categories],
    )
    if suggested_name:
        match = next((c for c in categories if c.name == suggested_name), None)
        receipt.suggested_category_id = match.id if match else None


async def upload_receipt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    filename: str | None,
    declared_content_type: str | None,
    content: bytes,
) -> ReceiptRead:
    content_type = _validate_upload(
        filename=filename, declared_content_type=declared_content_type, content=content
    )
    extension = _CONTENT_TYPE_TO_EXTENSION[content_type]

    storage_key = generate_storage_key(user_id, extension)
    storage = get_storage_provider()
    await storage.save(storage_key, content, content_type=content_type)

    repo = ReceiptRepository(db)
    receipt = Receipt(
        user_id=user_id,
        storage_key=storage_key,
        original_filename=sanitize_filename(filename),
        content_type=content_type,
        file_size_bytes=len(content),
        status=ReceiptStatus.PENDING,
    )
    repo.add(receipt)
    await repo.flush()

    await _run_ocr(db, receipt, content=content)
    await repo.flush()

    categories_by_id = await _categories_by_id(db, user_id)
    return _build_read(receipt, categories_by_id)


async def list_receipts(db: AsyncSession, *, user_id: uuid.UUID) -> list[ReceiptRead]:
    receipts = await ReceiptRepository(db).list_for_user(user_id)
    if not receipts:
        return []
    categories_by_id = await _categories_by_id(db, user_id)
    return [_build_read(r, categories_by_id) for r in receipts]


async def get_receipt(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID
) -> ReceiptRead:
    receipt = await ReceiptRepository(db).get_by_id_for_user(receipt_id, user_id)
    if receipt is None:
        raise NotFoundError("Receipt not found.")
    categories_by_id = await _categories_by_id(db, user_id)
    return _build_read(receipt, categories_by_id)


async def get_receipt_file(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID
) -> tuple[bytes, str, str | None]:
    """Returns (content, content_type, filename) for an authenticated,
    ownership-checked download/preview - there is no public URL for a
    receipt file; this is the only way to read one back."""
    receipt = await ReceiptRepository(db).get_by_id_for_user(receipt_id, user_id)
    if receipt is None:
        raise NotFoundError("Receipt not found.")
    storage = get_storage_provider()
    content = await storage.read(receipt.storage_key)
    return content, receipt.content_type, receipt.original_filename


async def confirm_receipt(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID, data: ReceiptConfirmRequest
) -> ReceiptRead:
    repo = ReceiptRepository(db)
    receipt = await repo.get_by_id_for_user(receipt_id, user_id)
    if receipt is None:
        raise NotFoundError("Receipt not found.")

    if data.category_id is not None:
        category = await CategoryRepository(db).get_visible_by_id(data.category_id, user_id)
        if category is None:
            raise ValidationAppError(
                "Category not found.", field_errors={"category_id": "not found"}
            )

    # Exactly what the user submitted - never merged with or defaulted
    # from extracted_*, so a correction can never be silently overwritten.
    receipt.confirmed_merchant = data.merchant
    receipt.confirmed_date = data.date
    receipt.confirmed_total_minor = data.total_minor
    receipt.confirmed_tax_minor = data.tax_minor
    receipt.confirmed_items = [item.model_dump() for item in data.items]
    receipt.category_id = data.category_id
    receipt.status = ReceiptStatus.CONFIRMED
    receipt.confirmed_at = datetime.now(UTC)

    await repo.flush()
    categories_by_id = await _categories_by_id(db, user_id)
    return _build_read(receipt, categories_by_id)


async def delete_receipt(db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID) -> None:
    repo = ReceiptRepository(db)
    receipt = await repo.get_by_id_for_user(receipt_id, user_id)
    if receipt is None:
        raise NotFoundError("Receipt not found.")

    storage = get_storage_provider()
    await storage.delete(receipt.storage_key)
    await repo.delete(receipt)
    await repo.flush()


async def create_transaction_from_receipt(
    db: AsyncSession, *, user_id: uuid.UUID, receipt_id: uuid.UUID, account_id: uuid.UUID
) -> TransactionRead:
    """Only ever reachable for a CONFIRMED receipt with a confirmed total -
    OCR output alone can never reach here, and this is a distinct,
    explicit action from confirming the receipt's data (Part 7)."""
    repo = ReceiptRepository(db)
    receipt = await repo.get_by_id_for_user(receipt_id, user_id)
    if receipt is None:
        raise NotFoundError("Receipt not found.")
    if receipt.status != ReceiptStatus.CONFIRMED:
        raise ValidationAppError("Confirm the receipt's details before creating a transaction.")
    if receipt.confirmed_total_minor is None or receipt.confirmed_total_minor <= 0:
        raise ValidationAppError(
            "The receipt needs a confirmed total before a transaction can be created.",
            field_errors={"total_minor": "required"},
        )
    if receipt.transaction_id is not None:
        raise ConflictError("A transaction has already been created from this receipt.")

    occurred_at = (
        datetime.combine(receipt.confirmed_date, time.min, tzinfo=UTC)
        if receipt.confirmed_date
        else datetime.now(UTC)
    )
    description = (
        f"Receipt: {receipt.original_filename}" if receipt.original_filename else "Receipt"
    )

    # Reuses the exact same validation/account/category handling and
    # authorization every other transaction goes through - never a second,
    # divergent way to create one.
    transaction = await transaction_service.create_transaction(
        db,
        user_id=user_id,
        data=TransactionCreate(
            account_id=account_id,
            type=TransactionType.EXPENSE,
            amount_minor=receipt.confirmed_total_minor,
            category_id=receipt.category_id,
            merchant=receipt.confirmed_merchant,
            description=description,
            occurred_at=occurred_at,
        ),
        idempotency_key=None,
    )
    receipt.transaction_id = transaction.id
    await repo.flush()
    return transaction
