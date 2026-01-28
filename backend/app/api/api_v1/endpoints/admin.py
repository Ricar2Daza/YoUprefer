from typing import Any, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.api import deps
from app.db.session import get_db
from app.models.profile import Profile
from app.services.season_service import season_service

router = APIRouter()

def check_admin(current_user: models.User = Depends(deps.get_current_user)):
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="The user doesn't have enough privileges"
        )
    return current_user

@router.get("/pending", response_model=List[schemas.Profile])
def get_pending_profiles(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Get all profiles pending for approval.
    """
    return db.query(Profile).filter(Profile.is_approved == False).all()

@router.post("/{profile_id}/approve", response_model=schemas.Profile)
def approve_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Approve a profile to be visible in rankings and duels.
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.is_approved = True
    db.commit()
    db.refresh(profile)
    return profile

@router.post("/{profile_id}/reject")
def reject_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Deactivate a profile if it doesn't meet requirements.
    """
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    profile.is_active = False
    db.commit()
    return {"status": "rejected"}

@router.post("/season/reset", response_model=List[schemas.Profile])
def reset_season(
    db: Session = Depends(get_db),
    admin_user: models.User = Depends(check_admin)
):
    """
    Manually trigger season reset (award badges + reset ELO).
    """
    next_season_name = f"Season_{datetime.now().strftime('%Y_%m_%d_%H%M')}"
    winners = season_service.reset_rankings_and_award_badges(db, next_season_name)
    return winners
