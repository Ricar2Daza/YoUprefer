from typing import List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from app import models, schemas
from app.api import deps
from app.db.session import get_db
from app.models.profile import Profile, ProfileType, Gender
from app.services.storage import storage_service

router = APIRouter()

@router.get("/pair", response_model=List[schemas.Profile])
def get_random_pair(
    type: ProfileType = ProfileType.REAL,
    gender: Gender = Gender.FEMALE,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional)
):
    """
    Get two random profiles of the same type and gender for comparison.
    """
    # Enforce REAL type for now as per requirements
    type = ProfileType.REAL
    
    query = db.query(Profile).filter(
        Profile.type == type,
        Profile.gender == gender,
        Profile.is_active == True,
        Profile.is_approved == True
    )
    
    if category_id:
        query = query.filter(Profile.category_id == category_id)

    # Filter out profiles the user has already voted on (if logged in)
    if current_user:
        from app.models.vote import Vote
        # Subquery to find all profile IDs the user has voted on (as winner or loser)
        voted_winner_ids = db.query(Vote.winner_id).filter(Vote.voter_id == current_user.id)
        voted_loser_ids = db.query(Vote.loser_id).filter(Vote.voter_id == current_user.id)
        
        query = query.filter(Profile.id.notin_(voted_winner_ids))
        query = query.filter(Profile.id.notin_(voted_loser_ids))
        
    profiles = query.order_by(func.random()).limit(2).all()
    
    if len(profiles) < 2:
        # Check if it's because they voted on everything
        if current_user:
            total_count = db.query(Profile).filter(
                Profile.type == type,
                Profile.gender == gender,
                Profile.is_active == True,
                Profile.is_approved == True
            ).count()
            if total_count >= 2:
                 # If we have enough profiles but query returned < 2, it means they voted on everything
                 raise HTTPException(status_code=404, detail="No more profiles to vote on! You've seen them all.")
        
        raise HTTPException(status_code=404, detail="Not enough profiles for comparison")
    
    return profiles

@router.post("/", response_model=Any) # Still Any because it returns upload_url too
def create_profile(
    profile_in: schemas.ProfileCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    """
    Create a new real profile for the current user.
    Returns a pre-signed URL for image upload.
    """
    if not profile_in.legal_consent:
        raise HTTPException(
            status_code=400, 
            detail="Legal consent is required to participate"
        )
    
    # Generate unique filename
    import uuid
    file_extension = profile_in.image_extension or "jpg"
    object_name = f"profiles/{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    # Resolve category
    cat_id = profile_in.category_id
    if not cat_id:
        # Default to General
        from app.models.category import Category
        general = db.query(Category).filter(Category.slug == "general").first()
        if general:
            cat_id = general.id

    # Create profile in DB (inactive until upload is confirmed or just active with placeholder)
    db_obj = Profile(
        type=ProfileType.REAL,
        gender=profile_in.gender,
        image_url=storage_service.get_public_url(object_name) or "",
        user_id=current_user.id,
        category_id=cat_id,
        legal_consent=True,
        legal_consent_at=func.now(),
        is_approved=False # User profiles need moderation
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    
    # Get pre-signed URL for the frontend
    upload_data = storage_service.get_presigned_url(object_name)
    
    if not upload_data:
         raise HTTPException(status_code=500, detail="Could not generate upload URL")

    return {
        "profile": db_obj,
        "upload_url": upload_data
    }

@router.post("/upload-direct")
async def upload_profile_direct(
    file: UploadFile = File(...),
    gender: str = Form(...),
    legal_consent: bool = Form(...),
    category_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    """
    Direct file upload endpoint (for development/testing).
    Uploads file to R2 and creates profile in one request.
    """
    from fastapi import UploadFile, File, Form
    
    if not legal_consent:
        raise HTTPException(status_code=400, detail="Legal consent is required")
    
    # Generate unique filename
    import uuid
    file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    object_name = f"profiles/{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    # Upload to R2
    file_content = await file.read()
    success = storage_service.upload_file(file_content, object_name, file.content_type)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload image")
    
    # Resolve category
    cat_id = category_id
    if not cat_id:
        # Default to General
        from app.models.category import Category
        general = db.query(Category).filter(Category.slug == "general").first()
        if general:
            cat_id = general.id

    # Create profile
    db_obj = Profile(
        type=ProfileType.REAL,
        gender=Gender(gender),
        image_url=storage_service.get_public_url(object_name) or "",
        user_id=current_user.id,
        category_id=cat_id,
        legal_consent=True,
        legal_consent_at=func.now(),
        is_approved=False
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    
    return {
        "id": db_obj.id,
        "type": db_obj.type,
        "gender": db_obj.gender,
        "image_url": db_obj.image_url,
        "elo_score": db_obj.elo_score,
        "is_approved": db_obj.is_approved,
        "message": "Profile created successfully"
    }

@router.get("/me", response_model=List[schemas.Profile])
def get_my_profiles(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    """
    Get all profiles belonging to the current user.
    """
    return db.query(Profile).filter(Profile.user_id == current_user.id).all()

@router.get("/ranking", response_model=List[schemas.Profile])
def get_ranking(
    type: ProfileType = ProfileType.REAL,
    gender: Gender = None,
    category_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """
    Get top rated profiles.
    """
    query = db.query(Profile).filter(
        Profile.type == type,
        Profile.is_active == True,
        Profile.is_approved == True
    )
    
    if gender:
        query = query.filter(Profile.gender == gender)
        
    if category_id:
        query = query.filter(Profile.category_id == category_id)
        
    return query.order_by(Profile.elo_score.desc()).limit(limit).all()

@router.delete("/{id}", response_model=schemas.Profile)
def delete_profile(
    *,
    db: Session = Depends(get_db),
    id: int,
    current_user: models.User = Depends(deps.get_current_user)
):
    """
    Delete a profile.
    """
    profile = db.query(Profile).filter(Profile.id == id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    if profile.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=400, detail="Not enough permissions")
        
    db.delete(profile)
    db.commit()
    return profile
