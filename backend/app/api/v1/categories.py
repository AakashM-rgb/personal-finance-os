"""Category endpoints. Every route is authenticated. Reads include system
defaults plus the caller's own custom categories; mutations only ever
succeed against categories the caller owns (see app.services.category_service)."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryUpdate
from app.services import category_service

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=None)
async def list_categories(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    categories = await category_service.list_categories(
        db, user_id=current_user.id, include_inactive=include_inactive
    )
    return {"data": categories, "error": None, "meta": {"count": len(categories)}}


@router.post("", response_model=None, status_code=201)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    category = await category_service.create_category(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": category, "error": None, "meta": None}


@router.get("/{category_id}", response_model=None)
async def get_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    category = await category_service.get_category(
        db, user_id=current_user.id, category_id=category_id
    )
    return {"data": category, "error": None, "meta": None}


@router.put("/{category_id}", response_model=None)
async def update_category(
    category_id: UUID,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    category = await category_service.update_category(
        db, user_id=current_user.id, category_id=category_id, data=body
    )
    await db.commit()
    return {"data": category, "error": None, "meta": None}


@router.delete("/{category_id}", response_model=None, status_code=200)
async def archive_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await category_service.archive_category(db, user_id=current_user.id, category_id=category_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
