from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models, schemas
from app.api import deps
from app.db.session import get_db
from app.services.voting_service import voting_service

from app.core.ratelimit import RateLimiter

router = APIRouter()

@router.post("/", response_model=schemas.Vote, dependencies=[Depends(RateLimiter(times=10, seconds=10))])
def cast_vote(
    vote_in: schemas.VoteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(deps.get_current_user)
):
    try:
        vote = voting_service.record_vote(
            db, 
            winner_id=vote_in.winner_id, 
            loser_id=vote_in.loser_id,
            voter_id=current_user.id
        )
        return vote
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
