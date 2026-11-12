"""Persistent user-defined merchant categorization rules - the reusable
memory behind "the user corrected this once, remember it":

    Transaction merchant text (raw narration or manually typed)
        -> app.services.merchant_normalization.normalize_merchant (the
           ONE normalization algorithm in this app - never a second one
           just for rules)
        -> canonical merchant_key
        -> upsert_rule / resolve_category_for_merchant

`resolve_category_for_merchant` is called by
app.services.sync_service._resolve_user_rule_category - tier 1 (the
highest-confidence source) of the sync categorization priority order.
`upsert_rule` is called both by the merchant-rules API
(app.api.v1.merchant_rules) for direct rule management, and by
app.services.transaction_service.update_transaction's opt-in
remember_category_for_merchant flag - the exact same function either way,
so a rule can never be created through two different code paths that
might normalize or validate differently.

A rule is ordinary user preference data, not a ledger record - it is
hard-deleted when removed, never soft-archived like a Category.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.category import Category
from app.models.merchant_category_rule import MerchantCategoryRule
from app.repositories.category_repository import CategoryRepository
from app.repositories.merchant_category_rule_repository import MerchantCategoryRuleRepository
from app.schemas.merchant_category_rule import MerchantCategoryRuleRead
from app.services.merchant_normalization import normalize_merchant


def _to_read(rule: MerchantCategoryRule, category: Category) -> MerchantCategoryRuleRead:
    return MerchantCategoryRuleRead(
        id=rule.id,
        merchant_key=rule.merchant_key,
        category_id=rule.category_id,
        category_name=category.name,
        category_icon=category.icon,
        category_color=category.color,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _get_owned_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID
) -> Category:
    category = await CategoryRepository(db).get_visible_by_id(category_id, user_id)
    if category is None:
        raise ValidationAppError("Category not found.", field_errors={"category_id": "not found"})
    return category


def normalize_merchant_key(raw_merchant: str) -> str:
    """The one place raw merchant text becomes a rule's merchant_key -
    reused by both the API layer and the sync/transaction integration
    points, so a caller can never accidentally store an un-normalized key."""
    return normalize_merchant(raw_merchant).canonical_name


async def list_rules(db: AsyncSession, *, user_id: uuid.UUID) -> list[MerchantCategoryRuleRead]:
    rules = await MerchantCategoryRuleRepository(db).list_for_user(user_id)
    if not rules:
        return []
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {category.id: category for category in categories}
    return [_to_read(rule, categories_by_id[rule.category_id]) for rule in rules]


async def get_rule(
    db: AsyncSession, *, user_id: uuid.UUID, rule_id: uuid.UUID
) -> MerchantCategoryRuleRead:
    rule = await MerchantCategoryRuleRepository(db).get_by_id_for_user(rule_id, user_id)
    if rule is None:
        raise NotFoundError("Merchant rule not found.")
    category = await _get_owned_category(db, user_id=user_id, category_id=rule.category_id)
    return _to_read(rule, category)


async def resolve_category_for_merchant(
    db: AsyncSession, *, user_id: uuid.UUID, canonical_merchant: str
) -> uuid.UUID | None:
    """Tier 1 of the sync categorization priority order - see
    app.services.sync_service._resolve_user_rule_category. `canonical_merchant`
    must already be normalized (the caller is expected to have called
    app.services.merchant_normalization.normalize_merchant itself, since
    the sync pipeline needs that same NormalizedMerchant result for its own
    confidence decision) - this never re-normalizes, to avoid computing it
    twice for the same transaction."""
    rule = await MerchantCategoryRuleRepository(db).get_by_user_and_merchant_key(
        user_id, canonical_merchant
    )
    return rule.category_id if rule is not None else None


async def upsert_rule(
    db: AsyncSession, *, user_id: uuid.UUID, raw_merchant: str, category_id: uuid.UUID
) -> MerchantCategoryRuleRead:
    """Creates a new rule, or - if one already exists for this user and
    merchant - repoints it to `category_id` instead of creating a
    duplicate (see app.models.merchant_category_rule's unique constraint,
    the actual backstop this pre-check-then-write pattern defers to under
    a genuine race)."""
    category = await _get_owned_category(db, user_id=user_id, category_id=category_id)
    merchant_key = normalize_merchant_key(raw_merchant)

    repo = MerchantCategoryRuleRepository(db)
    existing = await repo.get_by_user_and_merchant_key(user_id, merchant_key)
    if existing is not None:
        existing.category_id = category_id
        await repo.flush()
        return _to_read(existing, category)

    rule = MerchantCategoryRule(user_id=user_id, merchant_key=merchant_key, category_id=category_id)
    repo.add(rule)
    try:
        await repo.flush()
    except IntegrityError:
        # Genuine race: another request created the same (user_id,
        # merchant_key) rule concurrently between our pre-check and this
        # insert. The database's own unique constraint is what actually
        # prevents the duplicate row; this just turns it into an update
        # instead of a raw 500 - the same idempotent-replay pattern used
        # throughout this app (see transaction_service.create_transaction).
        await db.rollback()
        existing = await repo.get_by_user_and_merchant_key(user_id, merchant_key)
        if existing is None:
            raise
        existing.category_id = category_id
        await repo.flush()
        return _to_read(existing, category)

    return _to_read(rule, category)


async def update_rule_category(
    db: AsyncSession, *, user_id: uuid.UUID, rule_id: uuid.UUID, category_id: uuid.UUID
) -> MerchantCategoryRuleRead:
    repo = MerchantCategoryRuleRepository(db)
    rule = await repo.get_by_id_for_user(rule_id, user_id)
    if rule is None:
        raise NotFoundError("Merchant rule not found.")
    category = await _get_owned_category(db, user_id=user_id, category_id=category_id)
    rule.category_id = category_id
    await repo.flush()
    return _to_read(rule, category)


async def delete_rule(db: AsyncSession, *, user_id: uuid.UUID, rule_id: uuid.UUID) -> None:
    repo = MerchantCategoryRuleRepository(db)
    rule = await repo.get_by_id_for_user(rule_id, user_id)
    if rule is None:
        raise NotFoundError("Merchant rule not found.")
    await repo.delete(rule)
    await repo.flush()
