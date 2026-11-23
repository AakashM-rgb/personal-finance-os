"""Shared helpers for the F-001 credit-card correction tests: parse the
operator SQL scripts, and seed ledger rows as either backend booked them --
`book_old_code` moves the stored balance by the leg's cash-flow delta whatever
the account type (the bug), `book_fixed_code` moves a card by the amount owed.
Raw SQL, so the seeded state never depends on the current service code."""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REPO_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = REPO_ROOT / "scripts" / "sql"
IMPACT_SQL_PATH = SQL_DIR / "f001_card_ledger_impact_check.sql"
POST_MIGRATION_SQL_PATH = SQL_DIR / "f001_card_ledger_post_migration_check.sql"
PUBLIC_SCHEMA_SQL_PATH = SQL_DIR / "public_schema_exposure_check.sql"


def sql_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("--", 1)[0].rstrip()
        if line.strip():
            lines.append(line)
    return lines


def sql_body(path: Path) -> str:
    """The script without comments and psql meta-commands."""
    return "\n".join(line for line in sql_lines(path) if not line.lstrip().startswith("\\"))


def sql_statements(path: Path) -> list[str]:
    return [s.strip() for s in sql_body(path).split(";") if s.strip()]


def sql_queries(path: Path) -> list[str]:
    return [s for s in sql_statements(path) if s.upper().startswith(("SELECT", "WITH"))]


def as_json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


async def insert_user(db: AsyncSession) -> uuid.UUID:
    user_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, full_name, is_active) "
            "VALUES (:id, :email, 'x', 'F-001 Test', true)"
        ),
        {"id": user_id, "email": f"{user_id}@example.com"},
    )
    return user_id


async def insert_account(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    account_type: str,
    balance_minor: int,
    currency: str = "INR",
    credit_limit_minor: int | None = None,
) -> uuid.UUID:
    account_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO accounts (id, user_id, name, type, balance_minor, currency, is_active) "
            "VALUES (:id, :user_id, 'Account', :type, :balance, :currency, true)"
        ),
        {
            "id": account_id,
            "user_id": user_id,
            "type": account_type,
            "balance": balance_minor,
            "currency": currency,
        },
    )
    if credit_limit_minor is not None:
        await db.execute(
            text(
                "INSERT INTO credit_card_details (id, account_id, credit_limit_minor, "
                "statement_day, payment_due_day) VALUES (:id, :account_id, :limit, 5, 20)"
            ),
            {"id": uuid.uuid4(), "account_id": account_id, "limit": credit_limit_minor},
        )
    return account_id


async def book_old_code(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    tx_type: str,
    amount_minor: int,
    *,
    transfer_account_id: uuid.UUID | None = None,
) -> uuid.UUID:
    txn_id = await _insert_transaction(
        db, user_id, account_id, tx_type, amount_minor, transfer_account_id
    )
    source_delta = amount_minor if tx_type == "income" else -amount_minor
    await _adjust(db, account_id, source_delta)
    if transfer_account_id is not None:
        await _adjust(db, transfer_account_id, amount_minor)
    return txn_id


async def book_fixed_code(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    tx_type: str,
    amount_minor: int,
    *,
    transfer_account_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Book a leg the way the liability-aware backend does: on a card the amount
    owed moves opposite to the cash-flow delta, so a purchase raises it. Stands
    for activity that happened after the correction already ran."""
    txn_id = await _insert_transaction(
        db, user_id, account_id, tx_type, amount_minor, transfer_account_id
    )
    source_cash_flow = amount_minor if tx_type == "income" else -amount_minor
    await _adjust(db, account_id, await _owed_aware(db, account_id, source_cash_flow))
    if transfer_account_id is not None:
        await _adjust(
            db, transfer_account_id, await _owed_aware(db, transfer_account_id, amount_minor)
        )
    return txn_id


async def _owed_aware(db: AsyncSession, account_id: uuid.UUID, cash_flow_minor: int) -> int:
    account_type = await db.scalar(
        text("SELECT type FROM accounts WHERE id = :id"), {"id": account_id}
    )
    return -cash_flow_minor if account_type == "credit_card" else cash_flow_minor


async def backdate_ledger(db: AsyncSession, interval: str = "10 minutes") -> None:
    """Shift every ledger row and account timestamp back, so seeded legs sit
    clearly before a later correction run instead of inside its 60 s grace
    window. Accounts move with transactions, so updated_after_last_ledger_write
    is unaffected."""
    await db.execute(
        text(
            f"UPDATE transactions SET created_at = created_at - INTERVAL '{interval}', "
            f"updated_at = updated_at - INTERVAL '{interval}'"
        )
    )
    await db.execute(
        text(f"UPDATE accounts SET updated_at = updated_at - INTERVAL '{interval}'")
    )
    await db.commit()


async def _insert_transaction(
    db: AsyncSession,
    user_id: uuid.UUID,
    account_id: uuid.UUID,
    tx_type: str,
    amount_minor: int,
    transfer_account_id: uuid.UUID | None,
) -> uuid.UUID:
    currency = await db.scalar(
        text("SELECT currency FROM accounts WHERE id = :id"), {"id": account_id}
    )
    txn_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO transactions (id, user_id, account_id, transfer_account_id, type, "
            "amount_minor, currency, tags, occurred_at, is_recurring) VALUES (:id, :user_id, "
            ":account_id, :transfer_account_id, :type, :amount, :currency, '{}', now(), false)"
        ),
        {
            "id": txn_id,
            "user_id": user_id,
            "account_id": account_id,
            "transfer_account_id": transfer_account_id,
            "type": tx_type,
            "amount": amount_minor,
            "currency": currency,
        },
    )
    return txn_id


async def _adjust(db: AsyncSession, account_id: uuid.UUID, delta_minor: int) -> None:
    # Mirrors AccountRepository.adjust_balance, which also bumps updated_at.
    await db.execute(
        text(
            "UPDATE accounts SET balance_minor = balance_minor + :delta, updated_at = now() "
            "WHERE id = :id"
        ),
        {"delta": delta_minor, "id": account_id},
    )


async def balance(db: AsyncSession, account_id: uuid.UUID) -> int:
    value = await db.scalar(
        text("SELECT balance_minor FROM accounts WHERE id = :id"), {"id": account_id}
    )
    assert value is not None
    return int(value)


@dataclass(frozen=True)
class Scenario:
    """Two users' cards booked by the old code, with hand-computed results.

    Card A (INR, opened owing 50,000): expense 10,000, refund 2,000, bank -> A
    repayment 30,000, A -> bank cash advance 5,000, A -> B transfer 1,000.
    D = -10,000 + 2,000 + 30,000 - 5,000 - 1,000 = 16,000, so the old code
    stored 66,000; the amount owed is 50,000 - 16,000 = 34,000 (correction
    -32,000). Card B (INR, opened at 0) only received the 1,000 transfer:
    stored 1,000, actually a 1,000 credit balance (correction -2,000). Card C
    has no ledger activity. The other user's USD card (opened at 0) has one
    500 expense: stored -500, owed 500 (correction +1,000)."""

    card_a: uuid.UUID
    card_b: uuid.UUID
    card_c: uuid.UUID
    usd_card: uuid.UUID
    bank: uuid.UUID
    transaction_ids: frozenset[uuid.UUID]


SCENARIO_STORED = {"card_a": 66_000, "card_b": 1_000, "card_c": 7_000, "usd_card": -500}
SCENARIO_CORRECTED = {"card_a": 34_000, "card_b": -1_000, "card_c": 7_000, "usd_card": 500}
SCENARIO_BANK_BALANCE = 1_000_000 - 30_000 + 5_000


async def seed_scenario(db: AsyncSession) -> Scenario:
    user = await insert_user(db)
    other = await insert_user(db)
    bank = await insert_account(db, user, account_type="bank_account", balance_minor=1_000_000)
    card_a = await insert_account(
        db, user, account_type="credit_card", balance_minor=50_000, credit_limit_minor=200_000
    )
    card_b = await insert_account(
        db, user, account_type="credit_card", balance_minor=0, credit_limit_minor=100_000
    )
    card_c = await insert_account(
        db, user, account_type="credit_card", balance_minor=7_000, credit_limit_minor=100_000
    )
    usd_card = await insert_account(
        db, other, account_type="credit_card", balance_minor=0, currency="USD",
        credit_limit_minor=100_000,
    )
    txns = {
        await book_old_code(db, user, card_a, "expense", 10_000),
        await book_old_code(db, user, card_a, "income", 2_000),
        await book_old_code(db, user, bank, "transfer", 30_000, transfer_account_id=card_a),
        await book_old_code(db, user, card_a, "transfer", 5_000, transfer_account_id=bank),
        await book_old_code(db, user, card_a, "transfer", 1_000, transfer_account_id=card_b),
        await book_old_code(db, other, usd_card, "expense", 500),
    }
    await db.commit()
    return Scenario(card_a, card_b, card_c, usd_card, bank, frozenset(txns))
