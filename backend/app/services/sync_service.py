"""Automatic transaction sync orchestration - the ONLY caller of a
BankSyncProvider (see app.sync.provider.factory) and the ONLY place a
LinkedAccount/SyncRun row is created or mutated.

    BankSyncProvider (read-only, see app.sync.provider.base)
        -> fetch external transactions (trigger_sync)
        -> validate provider data
        -> normalize merchant (app.services.merchant_normalization)
        -> deduplicate (idempotency_key pre-check; the database's own
           unique constraint on Transaction.idempotency_key is the final
           race-safety backstop, exactly like offline/PWA sync)
        -> categorize (app.services.merchant_rule_service, then
           app.services.keyword_categorization)
        -> decide confidence
        -> transaction_service.create_transaction (the SAME path a
           manually-created transaction takes - there is no second,
           divergent ledger-writing path here)
        -> record SyncRun statistics

A high-confidence transaction (a confidently recognized merchant AND a
category resolved from a user rule or the known-merchant map) is created
with that category, never held back for review. A low-confidence
transaction is still created immediately - never silently guessed at or
dropped - but with category_id left NULL (the existing Uncategorized
convention, see app.services.category_service) and needs_review=True (see
app.models.transaction) so a later phase's review-queue UI can surface it.
A user's correction to a synced transaction goes through the existing
transaction_service.update_transaction like any other edit - nothing here
invents a second way to change one. When the user explicitly opts in
(TransactionUpdate.remember_category_for_merchant), that correction is
persisted as a MerchantCategoryRule (see app.services.merchant_rule_service)
and this module's own tier-1 categorization lookup (_resolve_user_rule_category)
applies it to every future synced transaction from the same merchant -
still fully deterministic, never an AI guess.

This module never identifies two transactions as a transfer - that stays
an explicit user action via the existing transaction-editing flow
(transaction_service.update_transaction), never a guess based on matching
a debit on one account against a credit on another.

Nothing here can ever initiate a payment, transfer, or withdrawal, or
touch a bank PIN/OTP/CVV/password: the provider Protocol every function in
this module depends on (BankSyncProvider) is permanently read-only - see
app.sync.provider.base.
"""

import enum
import hashlib
import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Literal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.account import AccountType
from app.models.linked_account import LinkedAccount, SyncConsentStatus
from app.models.sync_run import SyncRun, SyncRunStatus
from app.models.transaction import TransactionType
from app.repositories.category_repository import CategoryRepository
from app.repositories.linked_account_repository import LinkedAccountRepository
from app.repositories.sync_run_repository import SyncRunRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.account import AccountCreate
from app.schemas.sync import LinkedAccountRead, SyncRunRead
from app.schemas.transaction import TransactionCreate
from app.services import account_service, transaction_service
from app.services.audit_service import log_action
from app.services.keyword_categorization import (
    suggest_category_for_known_merchant,
    suggest_category_name,
)
from app.services.merchant_normalization import NormalizedMerchant, normalize_merchant
from app.services.merchant_rule_service import resolve_category_for_merchant
from app.sync.provider.base import ExternalTransaction, LinkedInstitutionAccount, LinkInitiation
from app.sync.provider.factory import get_sync_provider

logger = logging.getLogger("app.sync")

# How far back the very first sync for a newly linked account looks -
# every sync after that starts from the linked account's own
# last_synced_at instead, so a healthy account only ever re-fetches its
# own new activity, never its entire history again.
_DEFAULT_LOOKBACK_DAYS = 90

# Matches Transaction.idempotency_key's column width (see app.models.transaction).
_MAX_IDEMPOTENCY_KEY_LENGTH = 100


class CategorizationTier(enum.StrEnum):
    USER_RULE = "user_rule"
    MERCHANT_MAP = "merchant_map"
    KEYWORD = "keyword"
    NONE = "none"


class _IngestOutcome(enum.StrEnum):
    CREATED = "created"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    FAILED = "failed"


async def _resolve_user_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


def _parse_consent_status(value: str) -> SyncConsentStatus:
    try:
        return SyncConsentStatus(value)
    except ValueError:
        raise ValidationAppError(
            f"Unrecognized consent status from provider: {value!r}"
        ) from None


def _account_display_name(institution_account: LinkedInstitutionAccount) -> str:
    if institution_account.masked_account_ref:
        return f"{institution_account.institution_name} ({institution_account.masked_account_ref})"
    return institution_account.institution_name


def _linked_account_to_read(linked_account: LinkedAccount) -> LinkedAccountRead:
    return LinkedAccountRead.model_validate(linked_account)


async def _get_owned_linked_account(
    db: AsyncSession, *, user_id: uuid.UUID, linked_account_id: uuid.UUID
) -> LinkedAccount:
    linked_account = await LinkedAccountRepository(db).get_by_id_for_user(
        linked_account_id, user_id
    )
    if linked_account is None:
        raise NotFoundError("Linked account not found.")
    return linked_account


# --- link lifecycle ----------------------------------------------------------


async def initiate_link(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    institution_hint: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LinkInitiation:
    """No LinkedAccount is persisted here - the provider hands back
    everything the caller needs (a redirect_url and a consent_handle), and
    the caller passes that exact same consent_handle back to complete_link
    once the user returns from their bank/Account Aggregator app. `db` is
    only used for the audit log entry (see CLAUDE.md §12: audit sensitive
    actions), never for a linked-account row at this point."""
    provider = get_sync_provider()
    initiation = await provider.initiate_link(user_id=user_id, institution_hint=institution_hint)
    await log_action(
        db,
        user_id=user_id,
        action="linked_account.link_initiated",
        entity_type="linked_account",
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={"provider": provider.name},
    )
    return initiation


async def complete_link(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    consent_handle: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> list[LinkedAccountRead]:
    """Finishes a consent flow and persists one LinkedAccount row per
    institution account the provider reports, each auto-provisioned with
    its own new internal ledger Account (type=bank_account) so trigger_sync
    has somewhere real to post into immediately - never a payment
    capability, just an ordinary Account row exactly like one the user
    could have created by hand. Idempotent: completing the same handle
    twice (a retried callback) returns the already-linked rows instead of
    erroring or duplicating them, backed by the database's own unique
    constraint on (consent_id, external_account_id)."""
    provider = get_sync_provider()
    completion = await provider.complete_link(consent_handle=consent_handle)
    consent_status = _parse_consent_status(completion.consent_status)
    currency = await _resolve_user_currency(db, user_id)

    linked_repo = LinkedAccountRepository(db)
    results: list[LinkedAccountRead] = []

    for institution_account in completion.accounts:
        existing = await linked_repo.get_by_consent_and_external_account(
            consent_id=completion.consent_id,
            external_account_id=institution_account.external_account_id,
        )
        if existing is not None:
            results.append(_linked_account_to_read(existing))
            continue

        internal_account = await account_service.create_account(
            db,
            user_id=user_id,
            data=AccountCreate(
                name=_account_display_name(institution_account),
                type=AccountType.BANK_ACCOUNT,
                currency=currency,
                institution_name=institution_account.institution_name,
            ),
        )

        linked_account = LinkedAccount(
            user_id=user_id,
            account_id=internal_account.id,
            provider=provider.name,
            external_institution_name=institution_account.institution_name,
            external_account_id=institution_account.external_account_id,
            fip_reference=institution_account.fip_reference,
            consent_id=completion.consent_id,
            consent_status=consent_status,
            consent_expires_at=completion.consent_expires_at,
            masked_account_ref=institution_account.masked_account_ref,
        )
        linked_repo.add(linked_account)
        try:
            await linked_repo.flush()
        except IntegrityError:
            # Genuine race: another request completed the same handle
            # concurrently. The database's own unique constraint (see
            # app.models.linked_account) is what actually prevents the
            # duplicate row; this just turns it into an idempotent replay
            # rather than a raw 500.
            await db.rollback()
            existing = await linked_repo.get_by_consent_and_external_account(
                consent_id=completion.consent_id,
                external_account_id=institution_account.external_account_id,
            )
            if existing is None:
                raise
            linked_account = existing
        await log_action(
            db,
            user_id=user_id,
            action="linked_account.link_completed",
            entity_type="linked_account",
            entity_id=str(linked_account.id),
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"provider": provider.name},
        )
        results.append(_linked_account_to_read(linked_account))

    return results


async def list_linked_accounts(db: AsyncSession, *, user_id: uuid.UUID) -> list[LinkedAccountRead]:
    linked_accounts = await LinkedAccountRepository(db).list_for_user(user_id)
    return [_linked_account_to_read(linked_account) for linked_account in linked_accounts]


async def get_linked_account(
    db: AsyncSession, *, user_id: uuid.UUID, linked_account_id: uuid.UUID
) -> LinkedAccountRead:
    linked_account = await _get_owned_linked_account(
        db, user_id=user_id, linked_account_id=linked_account_id
    )
    return _linked_account_to_read(linked_account)


async def revoke_link(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    linked_account_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LinkedAccountRead:
    """Revokes the provider-side consent and marks the link revoked -
    never deletes the row (its sync history/provenance must survive, same
    reasoning as app.models.receipt keeping a receipt after its
    transaction is deleted) and never touches any transaction already
    imported through it."""
    linked_account = await _get_owned_linked_account(
        db, user_id=user_id, linked_account_id=linked_account_id
    )
    provider = get_sync_provider()
    await provider.revoke_consent(consent_id=linked_account.consent_id)
    linked_account.consent_status = SyncConsentStatus.REVOKED
    await LinkedAccountRepository(db).flush()
    await log_action(
        db,
        user_id=user_id,
        action="linked_account.revoked",
        entity_type="linked_account",
        entity_id=str(linked_account.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return _linked_account_to_read(linked_account)


async def update_linked_account_mapping(
    db: AsyncSession, *, user_id: uuid.UUID, linked_account_id: uuid.UUID, account_id: uuid.UUID
) -> LinkedAccountRead:
    """The only linked-account "management" mutation the service supports
    today: redirecting which of the user's own internal ledger accounts
    future syncs post into (e.g. after merging two accounts by hand). Reuses
    account_service.resolve_active_account - the exact same ownership+
    archived check transaction_service already depends on - so this can
    never point a linked account at another user's account or an archived
    one. Everything else about a LinkedAccount (consent_id, provider
    identifiers, sync statistics, ownership, consent_status) is never
    client-settable - see app.schemas.sync.LinkedAccountUpdate."""
    linked_account = await _get_owned_linked_account(
        db, user_id=user_id, linked_account_id=linked_account_id
    )
    await account_service.resolve_active_account(
        db, user_id=user_id, account_id=account_id, field="account_id"
    )
    linked_account.account_id = account_id
    await LinkedAccountRepository(db).flush()
    return _linked_account_to_read(linked_account)


# --- categorization ------------------------------------------------------------


async def _resolve_user_rule_category(
    db: AsyncSession, *, user_id: uuid.UUID, canonical_merchant: str
) -> uuid.UUID | None:
    """Tier 1 - the highest-confidence categorization source, and always
    checked first. Backed by app.services.merchant_rule_service - the
    user's own persistent "always categorize this merchant as..." memory,
    built from explicit corrections (see
    transaction_service.update_transaction's remember_category_for_merchant
    flag) or direct management (app.api.v1.merchant_rules). Never a guess:
    a miss here just falls through to the next tier."""
    return await resolve_category_for_merchant(
        db, user_id=user_id, canonical_merchant=canonical_merchant
    )


async def _categorize(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    normalized: NormalizedMerchant,
    category_names: list[str],
    category_id_by_name: dict[str, uuid.UUID],
) -> tuple[uuid.UUID | None, CategorizationTier]:
    """The categorization priority order: a user-defined rule (see
    _resolve_user_rule_category / app.services.merchant_rule_service), then
    a known-merchant mapping, then a generic keyword match, then
    Uncategorized. An AI-classifier tier is deliberately not implemented:
    app.ai.provider is
    a conversational tool-calling abstraction, not a one-shot deterministic
    classifier, and reusing it here would mean a non-deterministic,
    unnecessary external call for a decision this module can already make
    safely without one."""
    user_rule_category_id = await _resolve_user_rule_category(
        db, user_id=user_id, canonical_merchant=normalized.canonical_name
    )
    if user_rule_category_id is not None:
        return user_rule_category_id, CategorizationTier.USER_RULE

    if normalized.recognized:
        merchant_category_name = suggest_category_for_known_merchant(
            canonical_merchant=normalized.canonical_name, category_names=category_names
        )
        if merchant_category_name is not None:
            return category_id_by_name[merchant_category_name], CategorizationTier.MERCHANT_MAP

    keyword_category_name = suggest_category_name(
        merchant=normalized.canonical_name, item_descriptions=[], category_names=category_names
    )
    if keyword_category_name is not None:
        return category_id_by_name[keyword_category_name], CategorizationTier.KEYWORD

    return None, CategorizationTier.NONE


def _decide_confidence(
    normalized: NormalizedMerchant, tier: CategorizationTier
) -> Literal["high", "low"]:
    """A USER_RULE match is always high confidence: the user personally
    taught the app this exact merchant's category, which outranks
    normalize_merchant's own `recognized` flag entirely - a user rule for
    a merchant the curated alias list has never heard of (e.g. "ABC
    EDUCATION") must still auto-post, not sit in review waiting for a
    signal it will never get from the built-in list. A MERCHANT_MAP match
    additionally requires a confidently recognized merchant identity - it
    is curated, generic data, a weaker signal than something the user
    explicitly taught. The generic keyword match alone (only ever looked
    at free text, never a confirmed merchant identity) is never high
    confidence. Every other case (unknown merchant, keyword-only match, no
    match at all) is low confidence: category_id is left NULL and
    needs_review is set, never guessed."""
    if tier is CategorizationTier.USER_RULE:
        return "high"
    if tier is CategorizationTier.MERCHANT_MAP and normalized.recognized:
        return "high"
    return "low"


# --- idempotency / dedup --------------------------------------------------------


def _build_idempotency_key(linked_account_id: uuid.UUID, ext_txn: ExternalTransaction) -> str:
    """The primary key reuses the provider's own external transaction id
    verbatim (directly traceable back to the source system) when one
    exists. The fallback - used only when a provider omits an id - is a
    deterministic hash of the transaction's own fields, so re-fetching the
    exact same external transaction always derives the exact same key.
    Either form is hashed down rather than truncated when it would not fit
    the idempotency_key column, so two different long external ids that
    happen to share a prefix can never collide."""
    prefix = f"sync:{linked_account_id}:"

    if ext_txn.external_transaction_id:
        candidate = f"{prefix}{ext_txn.external_transaction_id}"
        if len(candidate) <= _MAX_IDEMPOTENCY_KEY_LENGTH:
            return candidate
        digest = hashlib.sha256(ext_txn.external_transaction_id.encode()).hexdigest()
        return f"{prefix}id:{digest}"[:_MAX_IDEMPOTENCY_KEY_LENGTH]

    basis = "|".join(
        [
            ext_txn.occurred_on.isoformat(),
            str(ext_txn.amount_minor),
            ext_txn.direction,
            ext_txn.narration,
        ]
    )
    digest = hashlib.sha256(basis.encode()).hexdigest()
    return f"{prefix}fallback:{digest}"[:_MAX_IDEMPOTENCY_KEY_LENGTH]


# --- pipeline --------------------------------------------------------------------


async def _ingest_one(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    linked_account: LinkedAccount,
    account_id: uuid.UUID,
    ext_txn: ExternalTransaction,
    category_names: list[str],
    category_id_by_name: dict[str, uuid.UUID],
) -> _IngestOutcome:
    # 1. Validate provider data - never trusted, even from our own mock.
    if ext_txn.external_account_id != linked_account.external_account_id:
        return _IngestOutcome.FAILED
    if ext_txn.direction not in ("debit", "credit"):
        return _IngestOutcome.FAILED

    # 2-3. Determine the internal account (passed in) and normalize the merchant.
    normalized = normalize_merchant(ext_txn.narration)

    # 4/6. Idempotency key and duplicate check - the pre-check here is only
    # for accurate SyncRun statistics; create_transaction's own
    # idempotency_key lookup (and the database's unique constraint behind
    # it) is what actually prevents a duplicate under a real race.
    idempotency_key = _build_idempotency_key(linked_account.id, ext_txn)
    existing = await TransactionRepository(db).get_by_idempotency_key(user_id, idempotency_key)
    if existing is not None:
        return _IngestOutcome.SKIPPED_DUPLICATE

    # 5. Categorize + decide confidence.
    category_id, tier = await _categorize(
        db,
        user_id=user_id,
        normalized=normalized,
        category_names=category_names,
        category_id_by_name=category_id_by_name,
    )
    confidence = _decide_confidence(normalized, tier)

    transaction_type = (
        TransactionType.EXPENSE if ext_txn.direction == "debit" else TransactionType.INCOME
    )

    try:
        data = TransactionCreate(
            account_id=account_id,
            type=transaction_type,
            amount_minor=ext_txn.amount_minor,
            category_id=category_id if confidence == "high" else None,
            merchant=normalized.canonical_name[:200],
            description=ext_txn.narration[:500],
            occurred_at=datetime.combine(ext_txn.occurred_on, time.min, tzinfo=UTC),
        )
    except PydanticValidationError:
        return _IngestOutcome.FAILED

    # 7-8. Create through the ONE ledger-writing path, then record provenance.
    try:
        await transaction_service.create_transaction(
            db,
            user_id=user_id,
            data=data,
            idempotency_key=idempotency_key,
            linked_account_id=linked_account.id,
            external_transaction_id=ext_txn.external_transaction_id or None,
            needs_review=(confidence == "low"),
        )
    except (ValidationAppError, NotFoundError):
        return _IngestOutcome.FAILED

    return _IngestOutcome.CREATED


def _decide_run_status(
    *, fetched: int, created: int, skipped: int, failed: int
) -> tuple[SyncRunStatus, str | None]:
    if failed == 0:
        return SyncRunStatus.SUCCESS, None
    if created > 0 or skipped > 0:
        message = f"{failed} of {fetched} fetched transactions failed validation and were skipped."
        return SyncRunStatus.PARTIAL, message
    return SyncRunStatus.FAILED, f"All {failed} fetched transactions failed validation."


async def trigger_sync(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    linked_account_id: uuid.UUID,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> SyncRunRead:
    """The sync pipeline entry point - see the module docstring for the
    full pipeline. A provider failure, or a per-transaction validation
    failure, is recorded on the SyncRun and never raised to the caller;
    existing transactions are never touched, and any transaction that DID
    succeed before a later failure is kept (see _decide_run_status)."""
    linked_account = await _get_owned_linked_account(
        db, user_id=user_id, linked_account_id=linked_account_id
    )
    if linked_account.account_id is None:
        raise ValidationAppError(
            "This linked account has no ledger account to sync into.",
            field_errors={"linked_account_id": "not mapped to an account"},
        )
    if linked_account.consent_status != SyncConsentStatus.ACTIVE:
        raise ValidationAppError(
            "This linked account's consent is not active.",
            field_errors={"linked_account_id": "consent not active"},
        )
    account_id = linked_account.account_id

    provider = get_sync_provider()
    started_at = datetime.now(UTC)
    sync_run = SyncRun(
        linked_account_id=linked_account.id, started_at=started_at, status=SyncRunStatus.SUCCESS
    )
    sync_run_repo = SyncRunRepository(db)
    sync_run_repo.add(sync_run)
    await sync_run_repo.flush()

    since = (
        linked_account.last_synced_at.date()
        if linked_account.last_synced_at is not None
        else started_at.date() - timedelta(days=_DEFAULT_LOOKBACK_DAYS)
    )
    until = started_at.date()

    logger.info(
        "sync_run_started",
        extra={
            "user_id": str(user_id),
            "linked_account_id": str(linked_account.id),
            "sync_run_id": str(sync_run.id),
        },
    )

    try:
        external_transactions = await provider.list_transactions(
            consent_id=linked_account.consent_id,
            external_account_id=linked_account.external_account_id,
            since=since,
            until=until,
        )
    except Exception as exc:  # noqa: BLE001 - a provider failure must never crash the sync
        sync_run.status = SyncRunStatus.FAILED
        sync_run.completed_at = datetime.now(UTC)
        # Never the exception's full payload/args (could echo provider
        # internals) - just its message, and capped to the column width.
        sync_run.error_message = f"Provider fetch failed: {exc}"[:500]
        linked_account.last_sync_status = SyncRunStatus.FAILED.value
        await sync_run_repo.flush()
        logger.error(
            "sync_run_provider_failed",
            extra={
                "user_id": str(user_id),
                "linked_account_id": str(linked_account.id),
                "sync_run_id": str(sync_run.id),
            },
        )
        await log_action(
            db,
            user_id=user_id,
            action="linked_account.sync_triggered",
            entity_type="linked_account",
            entity_id=str(linked_account.id),
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"sync_run_id": str(sync_run.id), "status": sync_run.status.value},
        )
        return SyncRunRead.model_validate(sync_run)

    sync_run.transactions_fetched = len(external_transactions)

    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=False)
    category_names = [category.name for category in categories]
    category_id_by_name = {category.name: category.id for category in categories}

    created_count = 0
    skipped_count = 0
    failed_count = 0
    for ext_txn in external_transactions:
        outcome = await _ingest_one(
            db,
            user_id=user_id,
            linked_account=linked_account,
            account_id=account_id,
            ext_txn=ext_txn,
            category_names=category_names,
            category_id_by_name=category_id_by_name,
        )
        if outcome is _IngestOutcome.CREATED:
            created_count += 1
        elif outcome is _IngestOutcome.SKIPPED_DUPLICATE:
            skipped_count += 1
        else:
            failed_count += 1

    sync_run.transactions_created = created_count
    sync_run.transactions_skipped_duplicate = skipped_count
    sync_run.completed_at = datetime.now(UTC)
    sync_run.status, sync_run.error_message = _decide_run_status(
        fetched=sync_run.transactions_fetched,
        created=created_count,
        skipped=skipped_count,
        failed=failed_count,
    )

    linked_account.last_synced_at = sync_run.completed_at
    linked_account.last_sync_status = sync_run.status.value

    await sync_run_repo.flush()

    logger.info(
        "sync_run_completed",
        extra={
            "user_id": str(user_id),
            "linked_account_id": str(linked_account.id),
            "sync_run_id": str(sync_run.id),
            "status": sync_run.status.value,
            "transactions_fetched": sync_run.transactions_fetched,
            "transactions_created": created_count,
            "transactions_skipped_duplicate": skipped_count,
            "transactions_failed": failed_count,
        },
    )
    await log_action(
        db,
        user_id=user_id,
        action="linked_account.sync_triggered",
        entity_type="linked_account",
        entity_id=str(linked_account.id),
        ip_address=ip_address,
        user_agent=user_agent,
        metadata={
            "sync_run_id": str(sync_run.id),
            "status": sync_run.status.value,
            "transactions_created": created_count,
            "transactions_skipped_duplicate": skipped_count,
        },
    )
    return SyncRunRead.model_validate(sync_run)


async def list_sync_runs(
    db: AsyncSession, *, user_id: uuid.UUID, linked_account_id: uuid.UUID
) -> list[SyncRunRead]:
    await _get_owned_linked_account(db, user_id=user_id, linked_account_id=linked_account_id)
    sync_runs = await SyncRunRepository(db).list_for_linked_account(linked_account_id)
    return [SyncRunRead.model_validate(sync_run) for sync_run in sync_runs]
