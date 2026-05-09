from datetime import datetime
from pydantic import BaseModel


class CustomVotePhoto(BaseModel):
    id: int
    participant_id: int
    image_url: str
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class CustomVoteParticipant(BaseModel):
    id: int
    vote_id: int
    user_id: int
    role: str
    joined_at: datetime | None = None
    photos: list[CustomVotePhoto] = []

    class Config:
        from_attributes = True


class CustomVote(BaseModel):
    id: int
    owner_id: int
    category_id: int
    title: str
    description: str | None = None
    is_active: bool
    created_at: datetime | None = None
    expires_at: datetime
    participants: list[CustomVoteParticipant] = []

    class Config:
        from_attributes = True


class CustomVoteVoteRequest(BaseModel):
    photo_id: int

