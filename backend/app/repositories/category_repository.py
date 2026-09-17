"""Data access for categories.

A category is "visible" to a user if it is a system default (user_id IS
NULL) or owned by that user. It is only mutable if owned by that user -
callers must use `get_owned_by_id` (not `get_visible_by_id`) before any
update/delete to enforce that system categories can never be modified.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category

_MAX_ANCESTOR_DEPTH = 50


class CategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_visible_for_user(
        self, user_id: uuid.UUID, *, include_inactive: bool
    ) -> list[Category]:
        stmt = (
            select(Category)
            .where((Category.user_id.is_(None)) | (Category.user_id == user_id))
            .order_by(Category.name.asc())
        )
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_visible_by_id(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> Category | None:
        stmt = select(Category).where(
            Category.id == category_id,
            (Category.user_id.is_(None)) | (Category.user_id == user_id),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_owned_by_id(self, category_id: uuid.UUID, user_id: uuid.UUID) -> Category | None:
        stmt = select(Category).where(Category.id == category_id, Category.user_id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_name_for_user(
        self, name: str, user_id: uuid.UUID, *, exclude_id: uuid.UUID | None = None
    ) -> Category | None:
        """Used to reject a duplicate name before insert/rename - only
        considers this user's own active categories (archived names are
        free to reuse; system categories are a separate namespace)."""
        stmt = select(Category).where(
            Category.user_id == user_id,
            Category.name == name,
            Category.is_active.is_(True),
        )
        if exclude_id is not None:
            stmt = stmt.where(Category.id != exclude_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_ancestor_ids(self, category_id: uuid.UUID) -> set[uuid.UUID]:
        """Walks parent_id up from `category_id`, returning every ancestor's id
        (not including category_id itself). Used to reject cycles before a
        parent_id is ever written."""
        ancestors: set[uuid.UUID] = set()
        current_id: uuid.UUID | None = category_id
        for _ in range(_MAX_ANCESTOR_DEPTH):
            category = await self._db.get(Category, current_id)
            if category is None or category.parent_id is None:
                break
            if category.parent_id in ancestors:
                break  # already-corrupt cycle in stored data; stop rather than loop forever
            ancestors.add(category.parent_id)
            current_id = category.parent_id
        return ancestors

    def add(self, category: Category) -> None:
        self._db.add(category)

    async def flush(self) -> None:
        await self._db.flush()
