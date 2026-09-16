"""Transaction business logic: validation, ownership enforcement, and the
account-balance ledger updates every create/update/delete/duplicate must
apply atomically and in the same spirit as the rest of the app - reads
never trust a caller-supplied user_id, only the authenticated one passed in
by the route layer.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.account import Account
from app.models.transaction import Transaction, TransactionType
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.transaction_repository import TransactionFilters, TransactionRepository
from app.schemas.transaction import (
    QuickAddParseResult,
    TransactionCreate,
    TransactionRead,
    TransactionUpdate,
)
from app.services import account_service
from app.services.quick_add_parser import parse_quick_add_text


def _to_read(transaction: Transaction) -> TransactionRead:
    return TransactionRead.model_validate(transaction)


async def _validate_shape(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    transfer_account_id: uuid.UUID | None,
    transaction_type: TransactionType,
    category_id: uuid.UUID | None,
) -> tuple[Account, Account | None]:
    account = await account_service.resolve_active_account(
        db, user_id=user_id, account_id=account_id, field="account_id"
    )

    if transaction_type == TransactionType.TRANSFER:
        if transfer_account_id is None:
            raise ValidationAppError(
                "A destination account is required for transfers.",
                field_errors={"transfer_account_id": "required"},
            )
        if transfer_account_id == account_id:
            raise ValidationAppError(
                "Choose a different destination account.",
                field_errors={"transfer_account_id": "same as source"},
            )
        transfer_account = await account_service.resolve_active_account(
            db,
            user_id=user_id,
            account_id=transfer_account_id,
            field="transfer_account_id",
        )
        if transfer_account.currency != account.currency:
            raise ValidationAppError(
                "Transfers between accounts in different currencies aren't supported yet.",
                field_errors={"transfer_account_id": "currency mismatch"},
            )
        if category_id is not None:
            raise ValidationAppError(
                "Transfers can't have a category.", field_errors={"category_id": "not applicable"}
            )
        return account, transfer_account

    if transfer_account_id is not None:
        raise ValidationAppError(
            "transfer_account_id is only valid for transfers.",
            field_errors={"transfer_account_id": "not applicable"},
        )
    if category_id is not None:
        category = await CategoryRepository(db).get_visible_by_id(category_id, user_id)
        if category is None:
            raise ValidationAppError(
                "Category not found.", field_errors={"category_id": "not found"}
            )
    return account, None


async def _apply_balance_effect(
    db: AsyncSession,
    *,
    account_id: uuid.UUID,
    transfer_account_id: uuid.UUID | None,
    transaction_type: TransactionType,
    amount_minor: int,
    sign: int,
) -> None:
    """sign=1 applies the transaction's effect on account balances; sign=-1
    reverses it (used before re-applying an edited transaction, and on delete)."""
    account_repo = AccountRepository(db)
    if transaction_type == TransactionType.EXPENSE:
        await account_repo.adjust_balance(account_id, -amount_minor * sign)
    elif transaction_type == TransactionType.INCOME:
        await account_repo.adjust_balance(account_id, amount_minor * sign)
    elif transaction_type == TransactionType.TRANSFER:
        assert transfer_account_id is not None
        await account_repo.adjust_balance(account_id, -amount_minor * sign)
        await account_repo.adjust_balance(transfer_account_id, amount_minor * sign)


async def list_transactions(
    db: AsyncSession, *, user_id: uuid.UUID, filters: TransactionFilters
) -> tuple[list[TransactionRead], int]:
    transactions, total = await TransactionRepository(db).list_for_user(user_id, filters)
    return [_to_read(t) for t in transactions], total


async def get_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> TransactionRead:
    transaction = await TransactionRepository(db).get_by_id_for_user(transaction_id, user_id)
    if transaction is None:
        raise NotFoundError("Transaction not found.")
    return _to_read(transaction)


async def create_transaction(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    data: TransactionCreate,
    idempotency_key: str | None,
    recurring_transaction_id: uuid.UUID | None = None,
) -> TransactionRead:
    """`recurring_transaction_id` is never accepted from the request body
    (TransactionCreate has no such field) - it is only ever passed by
    app.services.recurring_transaction_service when materializing a due
    occurrence, so a caller can never forge a link to another user's
    schedule. Every generated occurrence goes through this exact function,
    so it gets the same validation and account-balance effect as a
    manually-created transaction - never a second, divergent code path."""
    txn_repo = TransactionRepository(db)

    if idempotency_key:
        existing = await txn_repo.get_by_idempotency_key(user_id, idempotency_key)
        if existing is not None:
            return _to_read(existing)

    account, _transfer_account = await _validate_shape(
        db,
        user_id=user_id,
        account_id=data.account_id,
        transfer_account_id=data.transfer_account_id,
        transaction_type=data.type,
        category_id=data.category_id,
    )

    transaction = Transaction(
        user_id=user_id,
        account_id=data.account_id,
        transfer_account_id=data.transfer_account_id,
        category_id=data.category_id,
        type=data.type,
        amount_minor=data.amount_minor,
        currency=account.currency,
        merchant=data.merchant,
        description=data.description,
        notes=data.notes,
        payment_method=data.payment_method,
        tags=data.tags,
        occurred_at=data.occurred_at or datetime.now(UTC),
        is_recurring=data.is_recurring or recurring_transaction_id is not None,
        idempotency_key=idempotency_key,
        recurring_transaction_id=recurring_transaction_id,
    )
    txn_repo.add(transaction)
    try:
        await txn_repo.flush()
    except IntegrityError:
        # Only reachable via a genuine race: another request with the same
        # (user_id, idempotency_key) committed between our own "does this
        # already exist" check above and this insert - the database's own
        # unique constraint (not this code) is what actually prevents the
        # double-booking. Roll back this half-open transaction, then treat
        # it exactly like the ordinary idempotent-replay case: return the
        # row the other request created, never a raw 500 and never a
        # second transaction. See CLAUDE.md/offline-sync spec: "duplicate
        # requests return/use the original transaction result rather than
        # creating another transaction."
        await db.rollback()
        existing = (
            await txn_repo.get_by_idempotency_key(user_id, idempotency_key)
            if idempotency_key
            else None
        )
        if existing is None:
            raise
        return _to_read(existing)

    await _apply_balance_effect(
        db,
        account_id=data.account_id,
        transfer_account_id=data.transfer_account_id,
        transaction_type=data.type,
        amount_minor=data.amount_minor,
        sign=1,
    )

    return _to_read(transaction)


async def update_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, transaction_id: uuid.UUID, data: TransactionUpdate
) -> TransactionRead:
    txn_repo = TransactionRepository(db)
    transaction = await txn_repo.get_by_id_for_user(transaction_id, user_id)
    if transaction is None:
        raise NotFoundError("Transaction not found.")

    old_account_id = transaction.account_id
    old_transfer_account_id = transaction.transfer_account_id
    old_type = transaction.type
    old_amount_minor = transaction.amount_minor

    new_account_id = data.account_id if data.account_id is not None else old_account_id
    new_type = data.type if data.type is not None else old_type
    new_amount_minor = data.amount_minor if data.amount_minor is not None else old_amount_minor
    new_transfer_account_id = (
        data.transfer_account_id if data.transfer_account_id is not None else (
            old_transfer_account_id if new_type == TransactionType.TRANSFER else None
        )
    )
    if data.category_id is not None:
        new_category_id: uuid.UUID | None = data.category_id
    elif data.clear_category:
        new_category_id = None
    else:
        new_category_id = transaction.category_id

    account, _transfer_account = await _validate_shape(
        db,
        user_id=user_id,
        account_id=new_account_id,
        transfer_account_id=new_transfer_account_id,
        transaction_type=new_type,
        category_id=new_category_id,
    )

    await _apply_balance_effect(
        db,
        account_id=old_account_id,
        transfer_account_id=old_transfer_account_id,
        transaction_type=old_type,
        amount_minor=old_amount_minor,
        sign=-1,
    )
    await _apply_balance_effect(
        db,
        account_id=new_account_id,
        transfer_account_id=new_transfer_account_id,
        transaction_type=new_type,
        amount_minor=new_amount_minor,
        sign=1,
    )

    transaction.account_id = new_account_id
    transaction.transfer_account_id = new_transfer_account_id
    transaction.type = new_type
    transaction.amount_minor = new_amount_minor
    transaction.category_id = new_category_id
    transaction.currency = account.currency

    if data.merchant is not None:
        transaction.merchant = data.merchant
    if data.description is not None:
        transaction.description = data.description
    if data.notes is not None:
        transaction.notes = data.notes
    if data.payment_method is not None:
        transaction.payment_method = data.payment_method
    if data.tags is not None:
        transaction.tags = data.tags
    if data.occurred_at is not None:
        transaction.occurred_at = data.occurred_at
    if data.is_recurring is not None:
        transaction.is_recurring = data.is_recurring

    await txn_repo.flush()
    return _to_read(transaction)


async def delete_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> None:
    txn_repo = TransactionRepository(db)
    transaction = await txn_repo.get_by_id_for_user(transaction_id, user_id)
    if transaction is None:
        raise NotFoundError("Transaction not found.")

    await _apply_balance_effect(
        db,
        account_id=transaction.account_id,
        transfer_account_id=transaction.transfer_account_id,
        transaction_type=transaction.type,
        amount_minor=transaction.amount_minor,
        sign=-1,
    )
    await txn_repo.delete(transaction)
    await txn_repo.flush()


async def duplicate_transaction(
    db: AsyncSession, *, user_id: uuid.UUID, transaction_id: uuid.UUID
) -> TransactionRead:
    txn_repo = TransactionRepository(db)
    original = await txn_repo.get_by_id_for_user(transaction_id, user_id)
    if original is None:
        raise NotFoundError("Transaction not found.")

    # Re-validate rather than trust the original's already-committed state -
    # the account/category may have been archived or deleted since.
    account, _transfer_account = await _validate_shape(
        db,
        user_id=user_id,
        account_id=original.account_id,
        transfer_account_id=original.transfer_account_id,
        transaction_type=original.type,
        category_id=original.category_id,
    )

    duplicate = Transaction(
        user_id=user_id,
        account_id=original.account_id,
        transfer_account_id=original.transfer_account_id,
        category_id=original.category_id,
        type=original.type,
        amount_minor=original.amount_minor,
        currency=account.currency,
        merchant=original.merchant,
        description=original.description,
        notes=original.notes,
        payment_method=original.payment_method,
        tags=list(original.tags),
        # A duplicate is a new occurrence, not a copy of the old date.
        occurred_at=datetime.now(UTC),
        is_recurring=original.is_recurring,
        idempotency_key=None,
    )
    txn_repo.add(duplicate)
    await txn_repo.flush()

    await _apply_balance_effect(
        db,
        account_id=duplicate.account_id,
        transfer_account_id=duplicate.transfer_account_id,
        transaction_type=duplicate.type,
        amount_minor=duplicate.amount_minor,
        sign=1,
    )

    return _to_read(duplicate)


async def quick_add_parse(
    db: AsyncSession, *, user_id: uuid.UUID, text: str
) -> QuickAddParseResult:
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=False)
    custom_by_name = {c.name: c.id for c in categories if c.user_id is not None}
    system_by_name = {c.name: c.id for c in categories if c.user_id is None}
    parsed = parse_quick_add_text(text, list(custom_by_name), list(system_by_name))

    # Look up the id in the same tier order the parser matched in, so a
    # same-named custom/system category pair can never resolve to the
    # wrong row.
    category_id = None
    if parsed.category_name is not None:
        category_id = custom_by_name.get(parsed.category_name) or system_by_name.get(
            parsed.category_name
        )

    return QuickAddParseResult(
        raw_text=text,
        amount_minor=parsed.amount_minor,
        category_id=category_id,
        category_name=parsed.category_name,
        description=parsed.description,
        occurred_at=datetime.now(UTC),
        confidence=parsed.confidence,
        error=parsed.error,
    )
