from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel

# Forward references to avoid circular imports if necessary, 
# but for now we'll define minimal schemas or import them if safe.
# To be safe against circular imports, we can use string forward references 
# or import inside the method, but Pydantic handles this well usually.
from app.schemas.profile import Profile
from app.schemas.comment import Comment


class ReportBase(BaseModel):
    target_profile_id: Optional[int] = None
    target_user_id: Optional[int] = None
    target_comment_id: Optional[int] = None
    reason: str
    description: Optional[str] = None


class ReportCreate(ReportBase):
    pass


class ReportAppeal(BaseModel):
    reason: str


class UserBrief(BaseModel):
    """Solo columnas del modelo User, sin campos computados que requieran
    lazy-loading (evita MissingGreenlet al serializar en contexto async)."""
    id: int
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class Report(ReportBase):
    id: int
    reporter_id: int
    status: Literal["pending", "reviewed", "dismissed", "appealed"]
    created_at: datetime
    resolved_at: Optional[datetime] = None
    appeal_reason: Optional[str] = None
    appealed_at: Optional[datetime] = None
    reporter: Optional[UserBrief] = None
    target_profile: Optional[Profile] = None
    target_user: Optional[UserBrief] = None
    target_comment: Optional[Comment] = None

    class Config:
        from_attributes = True

