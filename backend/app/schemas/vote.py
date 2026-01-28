from typing import Optional
from pydantic import BaseModel

# Vote schemas
class VoteBase(BaseModel):
    winner_id: int
    loser_id: int

class VoteCreate(VoteBase):
    pass

class Vote(VoteBase):
    id: int
    voter_id: Optional[int]

    class Config:
        from_attributes = True
