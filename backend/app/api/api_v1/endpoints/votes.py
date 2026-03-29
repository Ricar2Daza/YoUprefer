from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.services.voting_service import voting_service

from app.core.ratelimit import RateLimiter

router = APIRouter()

@router.post("/", response_model=schemas.Vote, dependencies=[Depends(RateLimiter(times=10, seconds=10))])
async def cast_vote(
    vote_in: schemas.VoteCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Emitir un voto entre dos perfiles (winner/loser).
    Autenticación requerida. Ya no exige tener foto propia activa/aprobada para votar.
    """
    try:
        vote = await voting_service.record_vote(
            db, 
            winner_id=vote_in.winner_id, 
            loser_id=vote_in.loser_id,
            voter_id=current_user.id
        )
        return vote
    except ValueError as e:
        msg = str(e)
        if "Ya has votado" in msg:
            raise HTTPException(status_code=409, detail=msg)
        raise HTTPException(status_code=404, detail=msg)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
