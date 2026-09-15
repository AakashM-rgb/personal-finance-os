"""Account business logic: validation, ownership enforcement, and the
credit-utilization calculations shown to the user."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.account import Account, AccountType
from app.models.credit_card_details import CreditCardDetails
from app.repositories.account_repository import AccountRepository
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate, CreditCardDetailsRead


def calculate_credit_utilization_percent(balance_minor: int, credit_limit_minor: int) -> float:
    """The one canonical utilization formula - reused by the account API
    response and by the dashboard's health score, so the two can never
    silently diverge."""
    if credit_limit_minor <= 0:
        return 0.0
    return round((balance_minor / credit_limit_minor) * 100, 2)


def _credit_card_read(details: CreditCardDetails, balance_minor: int) -> CreditCardDetailsRead:
    available_credit_minor = details.credit_limit_minor - balance_minor
    utilization_percent = calculate_credit_utilization_percent(
        balance_minor, details.credit_limit_minor
    )
    return CreditCardDetailsRead(
        credit_limit_minor=details.credit_limit_minor,
        statement_day=details.statement_day,
        payment_due_day=details.payment_due_day,
        minimum_payment_minor=details.minimum_payment_minor,
        available_credit_minor=available_credit_minor,
        utilization_percent=utilization_percent,
    )


def _to_read(account: Account) -> AccountRead:
    return AccountRead(
        id=account.id,
        name=account.name,
        type=account.type,
        balance_minor=account.balance_minor,
        currency=account.currency,
        institution_name=account.institution_name,
        is_active=account.is_active,
        credit_card=(
            _credit_card_read(account.credit_card, account.balance_minor)
            if account.credit_card is not None
            else None
        ),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


async def list_accounts(
    db: AsyncSession, *, user_id: uuid.UUID, include_inactive: bool = False
) -> list[AccountRead]:
    accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=include_inactive)
    return [_to_read(account) for account in accounts]


async def get_account(
    db: AsyncSession, *, user_id: uuid.UUID, account_id: uuid.UUID
) -> AccountRead:
    account = await AccountRepository(db).get_by_id_for_user(account_id, user_id)
    if account is None:
        raise NotFoundError("Account not found.")
    return _to_read(account)


async def create_account(
    db: AsyncSession, *, user_id: uuid.UUID, data: AccountCreate
) -> AccountRead:
    account = Account(
        user_id=user_id,
        name=data.name,
        type=data.type,
        balance_minor=data.balance_minor,
        currency=data.currency,
        institution_name=data.institution_name,
    )
    # Explicitly set to None (not just omitted) so the relationship is
    # already "loaded" once this object is persistent - otherwise reading
    # account.credit_card later triggers an async-incompatible lazy load.
    account.credit_card = (
        CreditCardDetails(
            credit_limit_minor=data.credit_card.credit_limit_minor,
            statement_day=data.credit_card.statement_day,
            payment_due_day=data.credit_card.payment_due_day,
            minimum_payment_minor=data.credit_card.minimum_payment_minor,
        )
        if data.credit_card is not None
        else None
    )

    repo = AccountRepository(db)
    repo.add(account)
    await repo.flush()
    return _to_read(account)


async def update_account(
    db: AsyncSession, *, user_id: uuid.UUID, account_id: uuid.UUID, data: AccountUpdate
) -> AccountRead:
    repo = AccountRepository(db)
    account = await repo.get_by_id_for_user(account_id, user_id)
    if account is None:
        raise NotFoundError("Account not found.")

    if data.name is not None:
        account.name = data.name
    if data.balance_minor is not None:
        account.balance_minor = data.balance_minor
    if data.currency is not None:
        account.currency = data.currency
    if data.institution_name is not None:
        account.institution_name = data.institution_name

    if data.credit_card is not None:
        if account.type != AccountType.CREDIT_CARD:
            raise ValidationAppError(
                "credit_card details are only valid for a credit_card account",
                field_errors={"credit_card": "not applicable for this account type"},
            )
        if account.credit_card is None:
            account.credit_card = CreditCardDetails(account_id=account.id)
        account.credit_card.credit_limit_minor = data.credit_card.credit_limit_minor
        account.credit_card.statement_day = data.credit_card.statement_day
        account.credit_card.payment_due_day = data.credit_card.payment_due_day
        account.credit_card.minimum_payment_minor = data.credit_card.minimum_payment_minor

    await repo.flush()
    return _to_read(account)


async def archive_account(db: AsyncSession, *, user_id: uuid.UUID, account_id: uuid.UUID) -> None:
    repo = AccountRepository(db)
    account = await repo.get_by_id_for_user(account_id, user_id)
    if account is None:
        raise NotFoundError("Account not found.")
    account.is_active = False
    await repo.flush()
