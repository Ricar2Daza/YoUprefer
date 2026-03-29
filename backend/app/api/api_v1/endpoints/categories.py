from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models, schemas
from app.api import deps
from app.models.category import Category

router = APIRouter()

@router.get("/", response_model=List[schemas.Category])
async def read_categories(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(deps.get_async_db),
):
    """
    Retrieve categories.
    """
    result = await db.execute(select(Category).filter(Category.is_active == True).offset(skip).limit(limit))
    categories = result.scalars().all()
    return categories

@router.post("/", response_model=schemas.Category)
async def create_category(
    category_in: schemas.CategoryCreate,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_active_superuser_async),
):
    """
    Create new category (superuser only).
    """
    result = await db.execute(select(Category).filter(Category.slug == category_in.slug))
    category = result.scalars().first()
    if category:
        raise HTTPException(
            status_code=400,
            detail="The category with this slug already exists in the system.",
        )
    category = Category(
        name=category_in.name,
        slug=category_in.slug,
        description=category_in.description,
        is_active=category_in.is_active,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category

