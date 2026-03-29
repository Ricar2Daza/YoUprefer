from typing import Optional
from pydantic import BaseModel
from datetime import datetime

class BadgeBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    icon: Optional[str] = None
    category: Optional[str] = "ranking"
    level: Optional[str] = "bronce"
    rarity: Optional[str] = "common"
    min_position: Optional[int] = None
    is_active: Optional[bool] = True

class BadgeCreate(BadgeBase):
    pass

class BadgeUpdate(BadgeBase):
    pass

class Badge(BadgeBase):
    id: int

    class Config:
        from_attributes = True

class UserBadgeBase(BaseModel):
    user_id: int
    badge_id: int
    profile_id: Optional[int] = None
    season_id: Optional[int] = None

class UserBadge(UserBadgeBase):
    id: int
    awarded_at: datetime
    badge: Badge

    class Config:
        from_attributes = True
