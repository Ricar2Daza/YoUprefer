from datetime import datetime
from pydantic import BaseModel


class UserBlock(BaseModel):
    id: int
    blocker_id: int
    blocked_id: int
    created_at: datetime | None = None

    class Config:
        from_attributes = True

