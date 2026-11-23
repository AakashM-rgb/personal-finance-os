"""Guards the F-001 lockstep deploy runbook in docs/DEPLOYMENT.md.

The runbook is the only thing standing between a correct migration and a wrong
deploy, and three of its earlier claims were wrong or missing: it told the
operator to use Render maintenance mode (unavailable on this service's plan),
it let maintenance mode be lifted without confirming which commit was live, and
it did not say what the manual-edit signals cannot see. These tests pin the
corrections so a future edit cannot quietly drop them, and keep the migration's
blocker names and the runbook in agreement.
"""

import re

import pytest

from tests.f001_ledger_seed import REPO_ROOT

RUNBOOK_PATH = REPO_ROOT / "docs" / "DEPLOYMENT.md"
MIGRATION_PATH = (
    REPO_ROOT / "backend" / "migrations" / "versions"
    / "c8e4a1f6b2d9_correct_credit_card_balances.py"
)
SECTION_HEADING = "### Lockstep deploy: credit-card ledger fix (F-001)"


@pytest.fixture(scope="module")
def runbook() -> str:
    """The lockstep section with runs of whitespace collapsed, so assertions
    match prose regardless of where the file happens to wrap a line."""
    text = RUNBOOK_PATH.read_text(encoding="utf-8")
    start = text.index(SECTION_HEADING)
    end = text.index("\n## ", start)
    return " ".join(text[start:end].split())


def test_every_migration_blocker_is_documented(runbook: str) -> None:
    blockers = set(
        re.findall(r'reasons\.append\("([a-z_]+)"\)', MIGRATION_PATH.read_text(encoding="utf-8"))
    )
    assert blockers, "no blockers found in the migration; the regex is stale"
    assert blockers == {
        "currency_mismatch",
        "balance_set_after_ledger_fix",
        "ledger_activity_since_previous_correction",
    }
    for name in blockers:
        assert name in runbook, f"blocker {name} is not documented in the runbook"


def test_h1_documents_the_re_upgrade_guard(runbook: str) -> None:
    assert "**Re-upgrading after a downgrade.**" in runbook
    assert "cards_with_activity_since_previous_correction" in runbook
    # The reason the guard exists: D would absorb legs the fixed code booked.
    assert "twice their amount" in runbook
    # And that a no-op first run still arms it, which is production's case.
    assert "`mode: none`" in runbook


def test_h1_documents_both_durable_records_and_the_rules_that_protect_them(
    runbook: str,
) -> None:
    assert "**Two records, because one can be deleted.**" in runbook
    records = runbook[runbook.index("**Two records, because one can be deleted.**") :]
    records = records[: records.index("Restoring the snapshot is the last resort")]
    assert "`data_correction_runs`" in records
    assert "whichever record is older" in records
    # The operational rules the guard depends on.
    assert "Never prune `audit_logs` or `data_correction_runs`" in records
    assert "does not drop `data_correction_runs`" in records
    assert "`alembic check`" in records
    # The irreducible limit must stay stated, with the test that pins it.
    assert "If every record of the run is destroyed" in records
    assert "test_guard_is_blind_only_if_every_record_of_the_run_is_destroyed" in records
    # And the script/migration asymmetry.
    assert "The migration is the authority; the script is advisory." in records


def test_h2_resume_gate_requires_the_live_commit_before_traffic_returns(runbook: str) -> None:
    assert "**The resume gate.**" in runbook
    gate = runbook[runbook.index("**The resume gate.**") :]
    gate = gate[: gate.index("**Wire up the health check.**")]
    # Resuming is gated, not merely recommended.
    assert "Do not un-suspend the service" in gate
    assert "until **every** one of these is true" in gate
    # The specific checks the gate exists for.
    assert "`list_deploys`" in gate and "`commit.id`" in gate
    assert "`status` is `live`" in gate
    assert "/api/v1/health" in gate
    assert "card_legs_written_in_window = 0" in gate
    assert "c8e4a1f6b2d9 (head)" in gate
    # A green deploy is explicitly not sufficient on its own.
    assert "not \"the deploy went green\"" in gate


def test_h2_resume_step_no_longer_lifts_traffic_unconditionally(runbook: str) -> None:
    # The old step 6 read "Resume. Turn off maintenance mode." with no precondition.
    assert "**Resume.** Turn off maintenance mode." not in runbook
    assert "only through the gate below" in runbook
    # A failed deploy must not be left serving the pre-fix code on corrected data.
    assert "Never leave a failed deploy serving" in runbook


def test_h3_documents_what_the_manual_edit_signals_cannot_see(runbook: str) -> None:
    assert "**Limits of detection.**" in runbook
    limits = runbook[runbook.index("**Limits of detection.**") :]
    limits = limits[: limits.index("**Reconciling a skipped card.**")]
    # The three blind spots.
    assert "before this fix shipped" in limits
    assert "deleted under the old code" in limits
    assert "within 60 s of a ledger write" in limits
    # And the conclusion an operator must not draw from a clean report.
    assert "no evidence of a manual edit" in limits
    assert "never as proof that none happened" in limits
    assert "`cards_possibly_edited_by_hand` is a *hint*, not a finding" in limits


def test_m2_documents_the_reconciliation_procedure_for_skipped_cards(runbook: str) -> None:
    assert "**Reconciling a skipped card.**" in runbook
    steps = runbook[runbook.index("**Reconciling a skipped card.**") :]
    steps = steps[: steps.index("**Rollback.**")]
    assert "card_balance_correction_skip=<account id>" in steps
    # Establish the balance from statements, not from D.
    assert "not from D" in steps
    # Set it through the application so it is audited, never by hand.
    assert "PUT /api/v1/accounts/{id}" in steps
    assert "Never `UPDATE accounts` by hand" in steps
    # Every blocker needs its own reconciliation note.
    for name in ("currency_mismatch", "balance_set_after_ledger_fix",
                 "ledger_activity_since_previous_correction"):
        assert name in steps, f"{name} has no reconciliation guidance"
    # Numbered steps 1-5 are all present.
    assert all(f" {n}. **" in steps for n in range(1, 6))


def test_m3_records_the_verified_render_facts_instead_of_assuming_them(runbook: str) -> None:
    assert "**Render specifics — verified, not assumed.**" in runbook
    # The service identity and plan the procedure depends on.
    assert "srv-db39m7flk1mc739t5g80" in runbook
    assert "**`free`**" in runbook
    # Maintenance mode is paid-only, quoted from Render's docs.
    assert "Maintenance mode is available only for paid web services." in runbook
    assert "cannot be used while the service is on `free`" in runbook
    # No SSH and no one-off jobs, so alembic has to run out of band.
    assert "Running one-off jobs" in runbook
    assert "**Migrate out of band.**" in runbook
    # The old-instance overlap, with the number that makes it concrete.
    assert "90 s" in runbook
    # Spin-down is not a write stop.
    assert "spun-down service is not a stopped service" in runbook
    # The suspension gate is a fact read off the API, not an assumption.
    assert '`"suspended": "suspended"`' in runbook


def test_m3_drops_the_claim_that_maintenance_mode_stops_both_instances(runbook: str) -> None:
    assert "stops traffic reaching both the old and the new instance" not in runbook
    assert "returns 503 only to the public internet" in runbook
