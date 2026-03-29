from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel

# Forward references to avoid circular imports if necessary, 
# but for now we'll define minimal schemas or import them if safe.
# To be safe against circular imports, we can use string forward references 
# or import inside the method, but Pydantic handles this well usually.
from app.schemas.user import User
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


class Report(ReportBase):
    id: int
    reporter_id: int
    status: Literal["pending", "reviewed", "dismissed"]
    created_at: datetime
    resolved_at: Optional[datetime] = None
    reporter: Optional[User] = None
    target_profile: Optional[Profile] = None
    target_user: Optional[User] = None
    target_comment: Optional[Comment] = None

    class Config:
        from_attributes = True

