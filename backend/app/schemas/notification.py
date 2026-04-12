from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Notification(BaseModel):
    id: int
    user_id: int
    type: str
    payload: Dict[str, Any]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationUpdate(BaseModel):
    is_read: Optional[bool] = None


class NotificationList(BaseModel):
    items: List[Notification]
    total: int
    limit: int
    offset: int
