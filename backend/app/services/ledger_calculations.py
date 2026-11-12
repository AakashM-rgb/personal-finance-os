"""The one canonical mapping from a transaction to account-balance deltas.

Every leg of a transaction has a *cash-flow delta*: the change it makes to
the user's money on that account (income +amount, expense -amount, transfer
source -amount, transfer destination +amount). Net worth changes by the sum
of a transaction's cash-flow deltas whatever the account types, so a card
repayment, a cash advance and a card-to-card transfer are exactly neutral.

What is *stored* in `accounts.balance_minor` depends on the account type:
an asset stores what the user holds (stored delta = cash-flow delta); a
credit card stores what the user owes (stored delta = -cash-flow delta), so
a card purchase raises the amount owed and a repayment or refund lowers it.
"""

import enum
from dataclasses import dataclass

from app.models.account import AccountType
from app.models.transaction import TransactionType

LIABILITY_ACCOUNT_TYPES: frozenset[AccountType] = frozenset({AccountType.CREDIT_CARD})


class LedgerLeg(enum.StrEnum):
    SOURCE = "source"
    DESTINATION = "destination"


@dataclass(frozen=True)
class BalanceDeltas:
    source_minor: int
    destination_minor: int | None


def is_liability(account_type: AccountType) -> bool:
    return account_type in LIABILITY_ACCOUNT_TYPES


def cash_flow_delta(transaction_type: TransactionType, amount_minor: int, leg: LedgerLeg) -> int:
    if leg == LedgerLeg.DESTINATION:
        if transaction_type != TransactionType.TRANSFER:
            raise ValueError("Only a transfer has a destination leg.")
        return amount_minor
    if transaction_type == TransactionType.INCOME:
        return amount_minor
    return -amount_minor


def stored_balance_delta(account_type: AccountType, cash_flow_delta_minor: int) -> int:
    return -cash_flow_delta_minor if is_liability(account_type) else cash_flow_delta_minor


def balance_deltas(
    transaction_type: TransactionType,
    amount_minor: int,
    *,
    account_type: AccountType,
    transfer_account_type: AccountType | None,
) -> BalanceDeltas:
    """Stored-balance deltas for applying a transaction once. Reversing it
    (on edit or delete) negates both."""
    source = stored_balance_delta(
        account_type, cash_flow_delta(transaction_type, amount_minor, LedgerLeg.SOURCE)
    )
    if transaction_type != TransactionType.TRANSFER:
        return BalanceDeltas(source_minor=source, destination_minor=None)
    if transfer_account_type is None:
        raise ValueError("A transfer needs a destination account type.")
    destination = stored_balance_delta(
        transfer_account_type,
        cash_flow_delta(transaction_type, amount_minor, LedgerLeg.DESTINATION),
    )
    return BalanceDeltas(source_minor=source, destination_minor=destination)
