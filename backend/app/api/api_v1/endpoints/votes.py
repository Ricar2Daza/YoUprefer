from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.services.season_service import season_service
from app.adapters.cache.ranking_cache import RankingCacheAdapter
from app.adapters.persistence.sqlalchemy.uow import SqlAlchemyUnitOfWork
from app.application.errors import ConflictError, NotFoundError, ValidationAppError
from app.application.use_cases.record_vote import RecordVoteCommand, RecordVoteUseCase

from app.core.ratelimit import RateLimiter
import logging

logger = logging.getLogger(__name__)

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
        await season_service.ensure_season_current(db)
        uow = SqlAlchemyUnitOfWork(db)
        use_case = RecordVoteUseCase(uow=uow, ranking_cache=RankingCacheAdapter())
        vote = await use_case.execute(
            RecordVoteCommand(
                winner_id=vote_in.winner_id,
                loser_id=vote_in.loser_id,
                voter_id=current_user.id,
            )
        )
        return vote
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationAppError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error recording vote")
        raise HTTPException(status_code=500, detail="Internal server error")
