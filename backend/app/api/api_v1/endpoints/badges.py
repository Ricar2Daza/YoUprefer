from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.services.badge_service import badge_service

router = APIRouter()

@router.get("/progress")
async def get_badge_progress(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Obtiene el mejor ranking actual del usuario para mostrar progreso.
    """
    best_rank = await badge_service.get_best_rank(db, current_user.id)
    return {"best_rank": best_rank}

@router.get("/", response_model=List[schemas.Badge])
async def read_badges(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Retrieve all available badges.
    """
    # Trigger initialization of default badges if they don't exist (lazy init for dev)
    await badge_service.init_default_badges(db)
    
    query = select(models.Badge).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.get("/me", response_model=List[schemas.UserBadge])
async def read_user_badges(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Retrieve badges for current user.
    """
    # Check for new badges based on current ranking
    # In a real app, this might be async or triggered by events, 
    # but for simplicity/responsiveness we check on profile view.
    try:
        await badge_service.check_and_award_badges(db, current_user.id)
    except Exception as e:
        print(f"Error checking badges: {e}")
        
    query = select(models.UserBadge).filter(models.UserBadge.user_id == current_user.id)
    # Eager load badge info
    from sqlalchemy.orm import selectinload
    query = query.options(selectinload(models.UserBadge.badge))
    
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/check", status_code=200)
async def check_badges(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Manually trigger badge check for current user.
    """
    await badge_service.check_and_award_badges(db, current_user.id)
    return {"message": "Badges checked successfully"}
