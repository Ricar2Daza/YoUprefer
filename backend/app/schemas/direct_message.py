from datetime import datetime
from pydantic import BaseModel


class DirectMessageBase(BaseModel):
    content: str


class DirectMessageCreate(DirectMessageBase):
    pass


class DirectMessage(BaseModel):
    id: int
    sender_id: int
    recipient_id: int
    content: str
    is_read: bool
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class DirectMessageThread(BaseModel):
    user_id: int
    last_message: DirectMessage
    unread_count: int = 0
