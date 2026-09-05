from typing import Any, List, Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel

from app import models, schemas
from app.api import deps
from app.models.profile import Profile
from app.models.comment import Comment
import logging
from app.services.season_service import season_service

logger = logging.getLogger(__name__)

router = APIRouter()

def check_admin(current_user: models.User = Depends(deps.get_current_user_async)):
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="The user doesn't have enough privileges"
        )
    return current_user


class BanRequest(BaseModel):
    days: Optional[int] = None
    reason: Optional[str] = None

@router.get("/pending", response_model=List[schemas.Profile])
async def get_pending_profiles(
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Get all profiles pending for approval.
    """
    result = await db.execute(select(Profile).filter(Profile.is_approved == False))
    return result.scalars().all()

@router.post("/{profile_id}/approve", response_model=schemas.Profile)
async def approve_profile(
    profile_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Approve a profile to be visible in rankings and duels.
    """
    result = await db.execute(select(Profile).filter(Profile.id == profile_id))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.is_approved = True
    await db.commit()
    await db.refresh(profile)
    try:
        from app.core.redis_client import redis_client
        if redis_client:
            for key in redis_client.scan_iter("ranking:*"):
                redis_client.delete(key)
            redis_client.delete(f"participation:{profile.user_id}")
    except Exception:
        logger.warning("Failed to invalidate cache after profile approval", exc_info=True)
    return profile

@router.post("/{profile_id}/reject")
async def reject_profile(
    profile_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Deactivate a profile if it doesn't meet requirements.
    """
    result = await db.execute(select(Profile).filter(Profile.id == profile_id))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.is_active = False
    await db.commit()
    try:
        from app.core.redis_client import redis_client
        if redis_client:
            redis_client.delete(f"participation:{profile.user_id}")
    except Exception:
        logger.warning("Failed to invalidate cache after profile rejection", exc_info=True)
    return {"status": "rejected"}

@router.post("/season/reset", response_model=List[schemas.Profile])
async def reset_season(
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Manually trigger season reset (award badges + reset ELO).
    """
    next_season_name = f"Season_{datetime.now().strftime('%Y_%m_%d_%H%M')}"
    winners = await season_service.async_reset_rankings_and_award_badges(db, next_season_name)
    return winners


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    payload: BanRequest,
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin),
) -> Any:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    u = result.scalars().first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u.is_banned = True
    u.ban_reason = payload.reason
    if payload.days is None:
        u.banned_until = None
    else:
        if payload.days <= 0:
            raise HTTPException(status_code=400, detail="days inválido")
        u.banned_until = datetime.now(timezone.utc) + timedelta(days=payload.days)
    db.add(u)
    await db.commit()
    return {"detail": "ok"}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin),
) -> Any:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    u = result.scalars().first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    u.is_banned = False
    u.banned_until = None
    u.ban_reason = None
    db.add(u)
    await db.commit()
    return {"detail": "ok"}

@router.delete("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment(
    comment_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    admin_user: models.User = Depends(check_admin)
) -> Any:
    """
    Delete a comment (admin only).
    """
    result = await db.execute(select(Comment).filter(Comment.id == comment_id))
    comment = result.scalars().first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comentario no encontrado")
    await db.delete(comment)
    await db.commit()
    return {"status": "deleted"}

