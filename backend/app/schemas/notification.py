from datetime import datetime
from typing import Any
from pydantic import BaseModel


class Notification(BaseModel):
    id: int
    user_id: int
    type: str
    payload: dict[str, Any]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationUpdate(BaseModel):
    is_read: bool | None = None


class NotificationList(BaseModel):
    items: list[Notification]
    total: int
    limit: int
    offset: int
