from datetime import datetime

from pydantic import BaseModel


class CommentBase(BaseModel):
    content: str


class CommentCreate(CommentBase):
    pass


class Comment(CommentBase):
    id: int
    profile_id: int
    user_id: int
    created_at: datetime

    class Config:
        from_attributes = True

