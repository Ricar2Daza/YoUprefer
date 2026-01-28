from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.api import deps
from app.db.session import get_db
from app.models.category import Category

router = APIRouter()

@router.get("/", response_model=List[schemas.Category])
def read_categories(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Retrieve categories.
    """
    categories = db.query(Category).filter(Category.is_active == True).offset(skip).limit(limit).all()
    return categories

@router.post("/", response_model=schemas.Category)
def create_category(
    category_in: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_active_superuser),
):
    """
    Create new category (superuser only).
    """
    category = db.query(Category).filter(Category.slug == category_in.slug).first()
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
    db.commit()
    db.refresh(category)
    return category
