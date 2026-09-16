"""Receipt endpoints. Every route is authenticated and scoped to the
caller's own receipts via app.services.receipt_service - a receipt id
alone is never enough to read, confirm, download, or delete one; ownership
is re-checked on every single call.

`/{receipt_id}/file` is the ONLY way to read a receipt's bytes back - it
is not a public URL (no StaticFiles mount exists anywhere in this app),
requires the same bearer auth as every other route, and only returns
User A's file to User A.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ValidationAppError
from app.models.user import User
from app.schemas.receipt import (
    RECEIPT_MAX_FILE_SIZE_BYTES,
    ReceiptConfirmRequest,
    ReceiptCreateTransactionRequest,
)
from app.services import receipt_service

router = APIRouter(prefix="/receipts", tags=["receipts"])

_UPLOAD_CHUNK_SIZE = 1024 * 1024


async def _read_upload_bounded(file: UploadFile) -> bytes:
    """Reads the upload in bounded chunks, aborting as soon as the size
    limit is exceeded - never buffers an arbitrarily large body into
    memory just to reject it afterward."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > RECEIPT_MAX_FILE_SIZE_BYTES:
            raise ValidationAppError(
                f"Files must be {RECEIPT_MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB or smaller.",
                field_errors={"file": "too_large"},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("", response_model=None)
async def list_receipts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    receipts = await receipt_service.list_receipts(db, user_id=current_user.id)
    return {"data": receipts, "error": None, "meta": {"count": len(receipts)}}


@router.post("/upload", response_model=None, status_code=201)
async def upload_receipt(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    content = await _read_upload_bounded(file)
    receipt = await receipt_service.upload_receipt(
        db,
        user_id=current_user.id,
        filename=file.filename,
        declared_content_type=file.content_type,
        content=content,
    )
    await db.commit()
    return {"data": receipt, "error": None, "meta": None}


@router.get("/{receipt_id}", response_model=None)
async def get_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    receipt = await receipt_service.get_receipt(db, user_id=current_user.id, receipt_id=receipt_id)
    return {"data": receipt, "error": None, "meta": None}


@router.get("/{receipt_id}/file")
async def get_receipt_file(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    content, content_type, filename = await receipt_service.get_receipt_file(
        db, user_id=current_user.id, receipt_id=receipt_id
    )
    headers = {"Content-Disposition": f'inline; filename="{filename}"'} if filename else {}
    return Response(content=content, media_type=content_type, headers=headers)


@router.put("/{receipt_id}/confirm", response_model=None)
async def confirm_receipt(
    receipt_id: UUID,
    body: ReceiptConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    receipt = await receipt_service.confirm_receipt(
        db, user_id=current_user.id, receipt_id=receipt_id, data=body
    )
    await db.commit()
    return {"data": receipt, "error": None, "meta": None}


@router.post("/{receipt_id}/transaction", response_model=None, status_code=201)
async def create_transaction_from_receipt(
    receipt_id: UUID,
    body: ReceiptCreateTransactionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transaction = await receipt_service.create_transaction_from_receipt(
        db, user_id=current_user.id, receipt_id=receipt_id, account_id=body.account_id
    )
    await db.commit()
    return {"data": transaction, "error": None, "meta": None}


@router.delete("/{receipt_id}", response_model=None, status_code=200)
async def delete_receipt(
    receipt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await receipt_service.delete_receipt(db, user_id=current_user.id, receipt_id=receipt_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
