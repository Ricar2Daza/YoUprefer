from datetime import datetime
from typing import List
from pydantic import BaseModel


class FollowBase(BaseModel):
    follower_id: int
    following_id: int


class FollowCreate(BaseModel):
    following_id: int


class Follow(FollowBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FollowingIds(BaseModel):
    following_ids: List[int]


class FollowStats(BaseModel):
    user_id: int
    follower_count: int
    following_count: int
    is_following: bool
    is_followed_by: bool
