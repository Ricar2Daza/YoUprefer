from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field

# Esquemas de Usuario
class UserBadgeBrief(BaseModel):
    name: str
    icon: Optional[str] = None
    season_name: Optional[str] = None
    profile_id: Optional[int] = None

class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = True
    is_superuser: bool = False
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

class UserCreate(UserBase):
    email: EmailStr
    password: str

class UserUpdate(UserBase):
    password: Optional[str] = None

class User(UserBase):
    id: Optional[int] = None
    votes_cast_count: int = 0
    badges_count: int = 0
    badges: List[UserBadgeBrief] = Field(default_factory=list)
    follower_count: int = 0
    following_count: int = 0

    class Config:
        from_attributes = True
