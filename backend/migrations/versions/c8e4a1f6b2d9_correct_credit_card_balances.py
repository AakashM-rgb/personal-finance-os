"""correct credit-card balances booked with asset signs (F-001)

Before the liability-aware ledger, every card leg moved `balance_minor` by its
cash-flow delta (income +, expense -, transfer source -, transfer destination +),
so a card's stored balance is `opening + D`, where D is the sum of those deltas.
The amount owed is `opening - D`, so each card needs a correction of `-2 * D`.
This is valid only for legs booked by the old code, which is why the new
backend must not serve traffic until this revision has run (docs/DEPLOYMENT.md,
"Lockstep deploy").

Safeguards (decision C):
- Upgrade refuses to change anything unless the operator passes
  `-x card_balance_correction=apply`. It is a no-op without the flag only when
  no card needs a correction.
- A card that can't be corrected safely blocks the whole upgrade: a leg in a
  currency other than the card's (the account's currency was edited), an
  `account.balance_updated` audit row (that row is only written by the fixed
  code, so the card has data the old-sign formula doesn't describe), or a leg
  written since a previous run of this revision (see below). Such a card must
  be reconciled by hand and excluded with
  `-x card_balance_correction_skip=<account id>[,<account id>...]`.
- D is only the old code's error while every leg was booked by the old code.
  Once this revision has run once, the fixed backend is live, so any leg
  written from (the *first* run − 60 s) onward carries the new sign and is
  already correct. Re-running the upgrade after a downgrade would fold those
  legs into D and move the balance by twice their amount, so a card with such
  a leg is blocked (`ledger_activity_since_previous_correction`). Every run
  leaves a record, including the `mode: none` run on a database with no cards,
  so the guard also covers cards first used after that run.
- That guard is only as good as the record it reads, so there are two, written
  in the same transaction as the correction: the
  `ledger.card_balance_correction` summary row in `audit_logs`, and a row in
  `data_correction_runs` (see RUN_TABLE below). The threshold is the earliest
  run either source knows about, so losing one does not re-arm the double
  correction. If *both* are destroyed there is nothing left to detect, which
  is why neither the app nor any job may prune them.
- What the blockers cannot see: a balance typed in through `PUT /accounts`
  *before* the fix shipped left no audit row at all (that audit is decision E,
  part of this same fix), so the only hint is the non-blocking
  `updated_after_last_ledger_write` signal, which a rename or a deleted
  transaction also triggers. A leg deleted by the old code leaves nothing
  behind either. Neither is detectable here; both are covered in
  docs/DEPLOYMENT.md under "Limits of detection".
- Every corrected or skipped card gets an audit row, plus one summary row, in
  the same transaction as the update; transactions are never touched.
- Downgrade is relative: it subtracts exactly the correction it recorded, so
  later ledger activity survives. It needs `-x card_balance_correction=revert`
  and refuses any card whose balance was set by hand after the correction.

Revision ID: c8e4a1f6b2d9
Revises: a3f9c1d2e7b4
Create Date: 2026-11-22 12:00:00.000000

"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "c8e4a1f6b2d9"
down_revision: str | Sequence[str] | None = "a3f9c1d2e7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MODE_ARG = "card_balance_correction"
SKIP_ARG = "card_balance_correction_skip"
# The durable record that this revision ran. The guard against a second
# correction (see the docstring) must not depend on `audit_logs` alone: nothing
# in the app deletes audit rows today, but a retention job, a manual cleanup or
# a partial restore would, and that would silently re-arm the double
# correction. This table exists only to answer "has this revision ever run?",
# is written in the same transaction as the correction, and is deliberately
# never dropped -- not even by `downgrade()`, which records the revert in it.
RUN_TABLE = "data_correction_runs"
_RUN_TABLE_DDL = (
    f"""
    CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
        id uuid PRIMARY KEY,
        revision varchar(32) NOT NULL,
        direction varchar(16) NOT NULL,
        mode varchar(16) NOT NULL,
        ran_at timestamptz NOT NULL DEFAULT now(),
        details jsonb NOT NULL DEFAULT '{{}}'::jsonb
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_{RUN_TABLE}_revision_ran_at
        ON {RUN_TABLE} (revision, ran_at)
    """,
)
# A ledger write bumps accounts.updated_at in the same DB transaction as the
# transaction row, a few milliseconds later. Anything well past that is some
# other edit to the account, possibly a hand-entered balance.
LEDGER_WRITE_GRACE = "60 seconds"

# Same legs and per-card figures as Part 2 of
# scripts/sql/f001_card_ledger_impact_check.sql, so what the operator reviews is
# what gets applied; tests/test_migration_card_balance_correction.py checks the
# two agree. SUM is cast back to BIGINT (PostgreSQL widens it to NUMERIC).
_CARD_IMPACT_SQL = f"""
WITH previous_run AS (
    -- The *earliest* evidence that this revision has run, from either record:
    -- the fix went live at the first run, so every card leg from then on was
    -- booked correctly. LEAST ignores NULLs, so one surviving source is
    -- enough and the guard only goes quiet if both are gone.
    SELECT LEAST(
        (SELECT MIN(ran_at) FROM {RUN_TABLE}
          WHERE revision = '{revision}' AND direction = 'upgrade'),
        (SELECT MIN(created_at) FROM audit_logs
          WHERE action = 'ledger.card_balance_correction'
            AND entity_type = 'migration' AND entity_id = '{revision}')
    ) AS ran_at
),
legs AS (
    SELECT t.account_id AS account_id,
           CASE t.type WHEN 'income' THEN t.amount_minor ELSE -t.amount_minor END AS cash_flow_minor,
           t.currency, t.updated_at
    FROM transactions t
    UNION ALL
    SELECT t.transfer_account_id, t.amount_minor, t.currency, t.updated_at
    FROM transactions t
    WHERE t.type = 'transfer' AND t.transfer_account_id IS NOT NULL
)
SELECT a.id AS account_id, a.user_id, a.currency, a.balance_minor, ccd.credit_limit_minor,
       COALESCE(SUM(l.cash_flow_minor), 0)::bigint AS cash_flow_delta_minor,
       COUNT(l.account_id) AS legs,
       COUNT(*) FILTER (WHERE l.account_id IS NOT NULL AND l.currency <> a.currency)
           AS currency_mismatch_legs,
       COUNT(*) FILTER (WHERE l.account_id IS NOT NULL
                          AND l.updated_at >= (SELECT ran_at FROM previous_run)
                                              - INTERVAL '{LEDGER_WRITE_GRACE}')
           AS legs_since_previous_correction,
       COALESCE(a.updated_at > MAX(l.updated_at) + INTERVAL '{LEDGER_WRITE_GRACE}', false)
           AS updated_after_last_ledger_write,
       EXISTS (SELECT 1 FROM audit_logs al
               WHERE al.action = 'account.balance_updated'
                 AND al.entity_type = 'account' AND al.entity_id = a.id::text)
           AS has_balance_audit
FROM accounts a
LEFT JOIN credit_card_details ccd ON ccd.account_id = a.id
LEFT JOIN legs l ON l.account_id = a.id
WHERE a.type = 'credit_card'
GROUP BY a.id, a.user_id, a.currency, a.balance_minor, ccd.credit_limit_minor, a.updated_at
"""


class CardBalanceCorrectionRefused(RuntimeError):
    """Raised before any write, so Alembic rolls back and the revision stays
    unapplied."""


@dataclass(frozen=True)
class _Args:
    mode: str | None
    skip: frozenset[uuid.UUID]


@dataclass(frozen=True)
class _CardImpact:
    account_id: uuid.UUID
    user_id: uuid.UUID
    currency: str
    balance_minor: int
    credit_limit_minor: int | None
    cash_flow_delta_minor: int
    legs: int
    currency_mismatch_legs: int
    legs_since_previous_correction: int
    updated_after_last_ledger_write: bool
    has_balance_audit: bool

    @property
    def correction_minor(self) -> int:
        return -2 * self.cash_flow_delta_minor

    @property
    def corrected_balance_minor(self) -> int:
        return self.balance_minor + self.correction_minor

    def blockers(self) -> list[str]:
        reasons = []
        if self.currency_mismatch_legs:
            reasons.append("currency_mismatch")
        if self.has_balance_audit:
            reasons.append("balance_set_after_ledger_fix")
        if self.legs_since_previous_correction:
            reasons.append("ledger_activity_since_previous_correction")
        return reasons

    def review_signals(self) -> list[str]:
        signals = []
        if self.corrected_balance_minor < 0:
            signals.append("credit_balance_after_correction")
        if self.credit_limit_minor and self.corrected_balance_minor > self.credit_limit_minor:
            signals.append("over_limit_after_correction")
        if self.updated_after_last_ledger_write:
            signals.append("updated_after_last_ledger_write")
        return signals


def _parse_args(allowed_mode: str) -> _Args:
    raw = context.get_x_argument(as_dictionary=True)
    unknown = {k for k in raw if k.startswith(MODE_ARG) and k not in (MODE_ARG, SKIP_ARG)}
    if unknown:
        raise CardBalanceCorrectionRefused(f"Unknown option(s): {', '.join(sorted(unknown))}.")
    mode = raw.get(MODE_ARG)
    if mode is not None and mode != allowed_mode:
        raise CardBalanceCorrectionRefused(
            f"-x {MODE_ARG} must be '{allowed_mode}' for this direction, got '{mode}'."
        )
    skip: set[uuid.UUID] = set()
    for item in (raw.get(SKIP_ARG) or "").split(","):
        if item.strip():
            try:
                skip.add(uuid.UUID(item.strip()))
            except ValueError as exc:
                raise CardBalanceCorrectionRefused(f"Invalid account id in -x {SKIP_ARG}.") from exc
    return _Args(mode=mode, skip=frozenset(skip))


def _require_online() -> None:
    if context.is_offline_mode():
        raise CardBalanceCorrectionRefused(
            "This revision reads live data; it can't be rendered as offline SQL."
        )


def _lock_ledger(bind: Connection) -> None:
    # Blocks every ledger write (including from a still-running old backend)
    # until this transaction ends, so the balances updated are exactly the
    # ones D was computed for. Fails fast rather than queueing behind traffic.
    bind.execute(sa.text("SET LOCAL lock_timeout = '10s'"))
    bind.execute(sa.text("LOCK TABLE accounts, transactions IN SHARE ROW EXCLUSIVE MODE"))
    bind.execute(sa.text("SET LOCAL lock_timeout TO DEFAULT"))


def _audit(
    bind: Connection,
    *,
    user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: dict[str, Any],
) -> None:
    bind.execute(
        sa.text(
            "INSERT INTO audit_logs (id, user_id, action, entity_type, entity_id, metadata_json) "
            "VALUES (:id, :user_id, :action, :entity_type, :entity_id, CAST(:metadata AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "user_id": user_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "metadata": json.dumps(metadata),
        },
    )


def _ensure_run_table(bind: Connection) -> None:
    """Create the durable run record if it is missing. Idempotent, so it is
    safe on a re-upgrade and on a database upgraded before this table existed."""
    for statement in _RUN_TABLE_DDL:
        bind.execute(sa.text(statement))


def _record_run(bind: Connection, *, direction: str, mode: str, details: dict[str, Any]) -> None:
    bind.execute(
        sa.text(
            f"INSERT INTO {RUN_TABLE} (id, revision, direction, mode, details) "
            "VALUES (:id, :revision, :direction, :mode, CAST(:details AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "revision": revision,
            "direction": direction,
            "mode": mode,
            "details": json.dumps(details),
        },
    )


def _ids(account_ids: Sequence[uuid.UUID]) -> str:
    return ", ".join(sorted(str(i) for i in account_ids))


def _check_skip_targets(skip: frozenset[uuid.UUID], eligible: set[uuid.UUID]) -> None:
    stray = skip - eligible
    if stray:
        raise CardBalanceCorrectionRefused(
            f"-x {SKIP_ARG} names account(s) with nothing to skip: {_ids(list(stray))}."
        )


def upgrade() -> None:
    _require_online()
    args = _parse_args("apply")
    bind = op.get_bind()
    _ensure_run_table(bind)
    _lock_ledger(bind)

    cards = [_CardImpact(**row._mapping) for row in bind.execute(sa.text(_CARD_IMPACT_SQL))]
    needing = [c for c in cards if c.cash_flow_delta_minor != 0]
    _check_skip_targets(args.skip, {c.account_id for c in needing})
    to_skip = [c for c in needing if c.account_id in args.skip]
    to_correct = [c for c in needing if c.account_id not in args.skip]

    blocked = [c for c in to_correct if c.blockers()]
    if blocked:
        details = "; ".join(f"{c.account_id} ({', '.join(c.blockers())})" for c in blocked)
        raise CardBalanceCorrectionRefused(
            f"{len(blocked)} credit card(s) can't be corrected automatically: {details}. "
            f"Reconcile each one by hand, then exclude it with -x {SKIP_ARG}=<id>[,<id>]. "
            "Nothing was changed."
        )
    if to_correct and args.mode != "apply":
        raise CardBalanceCorrectionRefused(
            f"{len(to_correct)} credit card(s) need a balance correction. Review "
            "scripts/sql/f001_card_ledger_impact_check.sql, then re-run with "
            f"-x {MODE_ARG}=apply. Nothing was changed."
        )

    totals: dict[str, int] = {}
    for card in to_correct:
        bind.execute(
            sa.text(
                "UPDATE accounts SET balance_minor = balance_minor + :correction, "
                "updated_at = now() WHERE id = :id"
            ),
            {"correction": card.correction_minor, "id": card.account_id},
        )
        totals[card.currency] = totals.get(card.currency, 0) + card.correction_minor
        _audit(
            bind,
            user_id=card.user_id,
            action="account.balance_corrected",
            entity_type="account",
            entity_id=str(card.account_id),
            metadata={
                "revision": revision,
                "currency": card.currency,
                "previous_balance_minor": card.balance_minor,
                "cash_flow_delta_minor": card.cash_flow_delta_minor,
                "correction_minor": card.correction_minor,
                "new_balance_minor": card.corrected_balance_minor,
                "ledger_legs": card.legs,
                "review_signals": card.review_signals(),
            },
        )
    for card in to_skip:
        _audit(
            bind,
            user_id=card.user_id,
            action="account.balance_correction_skipped",
            entity_type="account",
            entity_id=str(card.account_id),
            metadata={
                "revision": revision,
                "currency": card.currency,
                "balance_minor": card.balance_minor,
                "unapplied_correction_minor": card.correction_minor,
                "blockers": card.blockers(),
                "review_signals": card.review_signals(),
            },
        )
    mode = args.mode or "none"
    summary: dict[str, Any] = {
        "mode": mode,
        "cards_checked": len(cards),
        "cards_corrected": len(to_correct),
        "cards_skipped": len(to_skip),
        "correction_minor_by_currency": totals,
    }
    _audit(
        bind,
        user_id=None,
        action="ledger.card_balance_correction",
        entity_type="migration",
        entity_id=revision,
        metadata=summary,
    )
    _record_run(bind, direction="upgrade", mode=mode, details=summary)


def downgrade() -> None:
    _require_online()
    args = _parse_args("revert")
    bind = op.get_bind()
    _ensure_run_table(bind)
    _lock_ledger(bind)

    # Latest unreverted correction per account for this revision, joined to
    # the account as it is now (a deleted user's accounts are simply gone).
    rows = bind.execute(
        sa.text(
            """
            SELECT al.id AS audit_id, a.id AS account_id, a.user_id, a.balance_minor,
                   (al.metadata_json ->> 'correction_minor')::bigint AS correction_minor,
                   EXISTS (SELECT 1 FROM audit_logs later
                           WHERE later.action = 'account.balance_updated'
                             AND later.entity_type = 'account'
                             AND later.entity_id = al.entity_id
                             AND later.created_at > al.created_at) AS set_by_hand_since
            FROM audit_logs al
            JOIN accounts a ON a.id::text = al.entity_id
            WHERE al.action = 'account.balance_corrected'
              AND al.metadata_json ->> 'revision' = :revision
              AND NOT EXISTS (SELECT 1 FROM audit_logs r
                              WHERE r.action IN ('account.balance_correction_reverted',
                                                 'account.balance_correction_revert_skipped')
                                AND r.metadata_json ->> 'correction_audit_id' = al.id::text)
            """
        ),
        {"revision": revision},
    ).all()

    _check_skip_targets(args.skip, {row.account_id for row in rows})
    to_skip = [row for row in rows if row.account_id in args.skip]
    to_revert = [row for row in rows if row.account_id not in args.skip]

    conflicts = [row.account_id for row in to_revert if row.set_by_hand_since]
    if conflicts:
        raise CardBalanceCorrectionRefused(
            f"{len(conflicts)} credit card balance(s) were set by hand after the correction: "
            f"{_ids(conflicts)}. Reverting would overwrite the user's balance. Reconcile each "
            f"one, then exclude it with -x {SKIP_ARG}=<id>[,<id>]. Nothing was changed."
        )
    if to_revert and args.mode != "revert":
        raise CardBalanceCorrectionRefused(
            f"{len(to_revert)} credit card correction(s) would be reverted. Re-run with "
            f"-x {MODE_ARG}=revert to confirm. Nothing was changed."
        )

    for row in to_revert:
        bind.execute(
            sa.text(
                "UPDATE accounts SET balance_minor = balance_minor - :correction, "
                "updated_at = now() WHERE id = :id"
            ),
            {"correction": row.correction_minor, "id": row.account_id},
        )
        _audit(
            bind,
            user_id=row.user_id,
            action="account.balance_correction_reverted",
            entity_type="account",
            entity_id=str(row.account_id),
            metadata={
                "revision": revision,
                "correction_audit_id": str(row.audit_id),
                "previous_balance_minor": row.balance_minor,
                "reverted_correction_minor": row.correction_minor,
                "new_balance_minor": row.balance_minor - row.correction_minor,
            },
        )
    for row in to_skip:
        _audit(
            bind,
            user_id=row.user_id,
            action="account.balance_correction_revert_skipped",
            entity_type="account",
            entity_id=str(row.account_id),
            metadata={"revision": revision, "correction_audit_id": str(row.audit_id)},
        )
    mode = args.mode or "none"
    reverted_summary: dict[str, Any] = {
        "mode": mode,
        "cards_reverted": len(to_revert),
        "cards_skipped": len(to_skip),
    }
    _audit(
        bind,
        user_id=None,
        action="ledger.card_balance_correction_reverted",
        entity_type="migration",
        entity_id=revision,
        metadata=reverted_summary,
    )
    # The table is never dropped here: it is the only record that survives a
    # purge of audit_logs, and the re-upgrade guard reads it.
    _record_run(bind, direction="downgrade", mode=mode, details=reverted_summary)
