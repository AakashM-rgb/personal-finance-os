"""Category business logic: visibility (system vs. owned), ownership
enforcement for mutation, and parent-category cycle prevention.

The UNCATEGORIZED_* constants and display_* helpers are the one shared
"how do we show a transaction with no category" convention - reused by
budget_service, dashboard_service, and analytics_service so a transaction
with category_id=None is never dropped or labeled differently depending
on which module happens to be rendering it."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationError, NotFoundError, ValidationAppError
from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate

UNCATEGORIZED_NAME = "Uncategorized"
UNCATEGORIZED_ICON = "🏷️"
UNCATEGORIZED_COLOR = "#9CA3AF"


def display_name(category: Category | None) -> str:
    return category.name if category is not None else UNCATEGORIZED_NAME


def display_icon(category: Category | None) -> str:
    return category.icon if category is not None else UNCATEGORIZED_ICON


def display_color(category: Category | None) -> str:
    return category.color if category is not None else UNCATEGORIZED_COLOR


def _to_read(category: Category) -> CategoryRead:
    return CategoryRead(
        id=category.id,
        name=category.name,
        icon=category.icon,
        color=category.color,
        budget_minor=category.budget_minor,
        parent_id=category.parent_id,
        is_system=category.user_id is None,
        is_active=category.is_active,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


async def list_categories(
    db: AsyncSession, *, user_id: uuid.UUID, include_inactive: bool = False
) -> list[CategoryRead]:
    categories = await CategoryRepository(db).list_visible_for_user(
        user_id, include_inactive=include_inactive
    )
    return [_to_read(category) for category in categories]


async def get_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID
) -> CategoryRead:
    category = await CategoryRepository(db).get_visible_by_id(category_id, user_id)
    if category is None:
        raise NotFoundError("Category not found.")
    return _to_read(category)


async def _validate_parent_for_create(
    repo: CategoryRepository, *, user_id: uuid.UUID, parent_id: uuid.UUID | None
) -> None:
    if parent_id is None:
        return
    parent = await repo.get_visible_by_id(parent_id, user_id)
    if parent is None:
        raise ValidationAppError(
            "Parent category not found.", field_errors={"parent_id": "not found"}
        )


async def create_category(
    db: AsyncSession, *, user_id: uuid.UUID, data: CategoryCreate
) -> CategoryRead:
    repo = CategoryRepository(db)
    await _validate_parent_for_create(repo, user_id=user_id, parent_id=data.parent_id)

    category = Category(
        user_id=user_id,
        name=data.name,
        icon=data.icon,
        color=data.color,
        budget_minor=data.budget_minor,
        parent_id=data.parent_id,
    )
    repo.add(category)
    await repo.flush()
    return _to_read(category)


async def update_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID, data: CategoryUpdate
) -> CategoryRead:
    repo = CategoryRepository(db)

    # A system category is visible to everyone but owned by no one: reading
    # it succeeds, but any mutation must be rejected as forbidden rather than
    # silently applied or reported as "not found" (the user can see it exists).
    visible = await repo.get_visible_by_id(category_id, user_id)
    if visible is None:
        raise NotFoundError("Category not found.")
    if visible.user_id is None:
        raise AuthorizationError("System categories cannot be modified.")

    category = await repo.get_owned_by_id(category_id, user_id)
    if category is None:
        raise NotFoundError("Category not found.")

    if data.name is not None:
        category.name = data.name
    if data.icon is not None:
        category.icon = data.icon
    if data.color is not None:
        category.color = data.color
    if data.budget_minor is not None:
        category.budget_minor = data.budget_minor

    if data.parent_id is not None:
        if data.parent_id == category_id:
            raise ValidationAppError(
                "A category cannot be its own parent.", field_errors={"parent_id": "invalid"}
            )
        parent = await repo.get_visible_by_id(data.parent_id, user_id)
        if parent is None:
            raise ValidationAppError(
                "Parent category not found.", field_errors={"parent_id": "not found"}
            )
        ancestors_of_new_parent = await repo.get_ancestor_ids(data.parent_id)
        if category_id in ancestors_of_new_parent:
            raise ValidationAppError(
                "That would create a circular category hierarchy.",
                field_errors={"parent_id": "would create a cycle"},
            )
        category.parent_id = data.parent_id
    elif data.clear_parent:
        category.parent_id = None

    await repo.flush()
    return _to_read(category)


async def archive_category(
    db: AsyncSession, *, user_id: uuid.UUID, category_id: uuid.UUID
) -> None:
    repo = CategoryRepository(db)

    visible = await repo.get_visible_by_id(category_id, user_id)
    if visible is None:
        raise NotFoundError("Category not found.")
    if visible.user_id is None:
        raise AuthorizationError("System categories cannot be deleted.")

    category = await repo.get_owned_by_id(category_id, user_id)
    if category is None:
        raise NotFoundError("Category not found.")

    category.is_active = False
    await repo.flush()
