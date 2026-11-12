import pytest

from app.models.account import AccountType
from app.models.transaction import TransactionType
from app.services.ledger_calculations import (
    BalanceDeltas,
    LedgerLeg,
    balance_deltas,
    cash_flow_delta,
    is_liability,
    stored_balance_delta,
)

ASSET_TYPES = [t for t in AccountType if t != AccountType.CREDIT_CARD]
CARD = AccountType.CREDIT_CARD
BANK = AccountType.BANK_ACCOUNT


def _net_worth_change(
    transaction_type: TransactionType,
    amount_minor: int,
    account_type: AccountType,
    transfer_account_type: AccountType | None = None,
) -> int:
    """Net worth = assets - liabilities, so a stored delta on a card counts negated."""
    deltas = balance_deltas(
        transaction_type,
        amount_minor,
        account_type=account_type,
        transfer_account_type=transfer_account_type,
    )
    change = -deltas.source_minor if is_liability(account_type) else deltas.source_minor
    if deltas.destination_minor is not None:
        assert transfer_account_type is not None
        dest = deltas.destination_minor
        change += -dest if is_liability(transfer_account_type) else dest
    return change


def test_only_credit_cards_are_liabilities() -> None:
    assert is_liability(CARD)
    assert not any(is_liability(t) for t in ASSET_TYPES)


@pytest.mark.parametrize(
    ("transaction_type", "leg", "expected"),
    [
        (TransactionType.INCOME, LedgerLeg.SOURCE, 1000),
        (TransactionType.EXPENSE, LedgerLeg.SOURCE, -1000),
        (TransactionType.TRANSFER, LedgerLeg.SOURCE, -1000),
        (TransactionType.TRANSFER, LedgerLeg.DESTINATION, 1000),
    ],
)
def test_cash_flow_delta_per_leg(
    transaction_type: TransactionType, leg: LedgerLeg, expected: int
) -> None:
    assert cash_flow_delta(transaction_type, 1000, leg) == expected


@pytest.mark.parametrize("transaction_type", [TransactionType.INCOME, TransactionType.EXPENSE])
def test_non_transfer_has_no_destination_leg(transaction_type: TransactionType) -> None:
    with pytest.raises(ValueError):
        cash_flow_delta(transaction_type, 1000, LedgerLeg.DESTINATION)


@pytest.mark.parametrize("account_type", ASSET_TYPES)
def test_asset_stores_the_cash_flow_delta(account_type: AccountType) -> None:
    assert stored_balance_delta(account_type, 500) == 500
    assert stored_balance_delta(account_type, -500) == -500


def test_card_stores_the_negated_cash_flow_delta() -> None:
    assert stored_balance_delta(CARD, -500) == 500
    assert stored_balance_delta(CARD, 500) == -500


@pytest.mark.parametrize("account_type", ASSET_TYPES)
def test_asset_expense_and_income(account_type: AccountType) -> None:
    expense = balance_deltas(
        TransactionType.EXPENSE, 2500, account_type=account_type, transfer_account_type=None
    )
    income = balance_deltas(
        TransactionType.INCOME, 2500, account_type=account_type, transfer_account_type=None
    )
    assert expense == BalanceDeltas(source_minor=-2500, destination_minor=None)
    assert income == BalanceDeltas(source_minor=2500, destination_minor=None)


def test_card_purchase_increases_amount_owed_and_reduces_net_worth() -> None:
    deltas = balance_deltas(
        TransactionType.EXPENSE, 2500, account_type=CARD, transfer_account_type=None
    )
    assert deltas == BalanceDeltas(source_minor=2500, destination_minor=None)
    assert _net_worth_change(TransactionType.EXPENSE, 2500, CARD) == -2500


def test_card_refund_reduces_amount_owed_and_raises_net_worth() -> None:
    deltas = balance_deltas(
        TransactionType.INCOME, 2500, account_type=CARD, transfer_account_type=None
    )
    assert deltas == BalanceDeltas(source_minor=-2500, destination_minor=None)
    assert _net_worth_change(TransactionType.INCOME, 2500, CARD) == 2500


@pytest.mark.parametrize("source_type", ASSET_TYPES)
def test_card_repayment_reduces_both_balances_and_is_net_worth_neutral(
    source_type: AccountType,
) -> None:
    deltas = balance_deltas(
        TransactionType.TRANSFER, 2500, account_type=source_type, transfer_account_type=CARD
    )
    assert deltas == BalanceDeltas(source_minor=-2500, destination_minor=-2500)
    assert _net_worth_change(TransactionType.TRANSFER, 2500, source_type, CARD) == 0


def test_cash_advance_raises_both_balances_and_is_net_worth_neutral() -> None:
    deltas = balance_deltas(
        TransactionType.TRANSFER, 2500, account_type=CARD, transfer_account_type=BANK
    )
    assert deltas == BalanceDeltas(source_minor=2500, destination_minor=2500)
    assert _net_worth_change(TransactionType.TRANSFER, 2500, CARD, BANK) == 0


def test_card_to_card_transfer_moves_debt_and_is_net_worth_neutral() -> None:
    deltas = balance_deltas(
        TransactionType.TRANSFER, 2500, account_type=CARD, transfer_account_type=CARD
    )
    assert deltas == BalanceDeltas(source_minor=2500, destination_minor=-2500)
    assert _net_worth_change(TransactionType.TRANSFER, 2500, CARD, CARD) == 0


@pytest.mark.parametrize("source_type", ASSET_TYPES)
@pytest.mark.parametrize("destination_type", ASSET_TYPES)
def test_asset_to_asset_transfer_is_unchanged_and_neutral(
    source_type: AccountType, destination_type: AccountType
) -> None:
    deltas = balance_deltas(
        TransactionType.TRANSFER,
        2500,
        account_type=source_type,
        transfer_account_type=destination_type,
    )
    assert deltas == BalanceDeltas(source_minor=-2500, destination_minor=2500)
    assert _net_worth_change(TransactionType.TRANSFER, 2500, source_type, destination_type) == 0


@pytest.mark.parametrize("account_type", list(AccountType))
@pytest.mark.parametrize("transaction_type", [TransactionType.INCOME, TransactionType.EXPENSE])
def test_net_worth_change_equals_cash_flow_for_every_account_type(
    account_type: AccountType, transaction_type: TransactionType
) -> None:
    expected = cash_flow_delta(transaction_type, 777, LedgerLeg.SOURCE)
    assert _net_worth_change(transaction_type, 777, account_type) == expected


@pytest.mark.parametrize("account_type", list(AccountType))
@pytest.mark.parametrize("transfer_account_type", list(AccountType))
def test_every_transfer_is_net_worth_neutral(
    account_type: AccountType, transfer_account_type: AccountType
) -> None:
    change = _net_worth_change(
        TransactionType.TRANSFER, 123_456, account_type, transfer_account_type
    )
    assert change == 0


def test_transfer_without_destination_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        balance_deltas(
            TransactionType.TRANSFER, 1000, account_type=BANK, transfer_account_type=None
        )
