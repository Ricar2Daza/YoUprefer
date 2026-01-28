from typing import Optional
from pydantic import BaseModel
from datetime import datetime
from app.models.profile import ProfileType, Gender

# Profile schemas
class ProfileBase(BaseModel):
    type: ProfileType
    gender: Gender

class ProfileCreate(BaseModel):
    gender: Gender
    legal_consent: bool
    image_extension: Optional[str] = "jpg"
    category_id: Optional[int] = None

class ProfileUpdate(ProfileBase):
    image_url: Optional[str] = None
    elo_score: Optional[int] = None
    is_active: Optional[bool] = None
    is_approved: Optional[bool] = None
    category_id: Optional[int] = None

class Profile(ProfileBase):
    id: int
    image_url: str
    elo_score: int
    voted_count: int
    win_count: int
    user_id: Optional[int]
    category_id: Optional[int]
    is_active: bool
    is_approved: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
