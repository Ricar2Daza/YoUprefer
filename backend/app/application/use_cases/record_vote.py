from dataclasses import dataclass
import logging

from sqlalchemy.exc import IntegrityError

from app.application.errors import ConflictError, NotFoundError, ValidationAppError
from app.application.ports.ranking_cache import RankingCachePort
from app.application.ports.uow import UnitOfWorkPort
from app.domain.elo import calculate_elo
from app.models.vote import Vote

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecordVoteCommand:
    winner_id: int
    loser_id: int
    voter_id: int | None


class RecordVoteUseCase:
    def __init__(self, *, uow: UnitOfWorkPort, ranking_cache: RankingCachePort | None = None):
        self._uow = uow
        self._ranking_cache = ranking_cache

    async def execute(self, cmd: RecordVoteCommand) -> Vote:
        if cmd.winner_id == cmd.loser_id:
            raise ValidationAppError("winner_id y loser_id no pueden ser iguales")

        async with self._uow:
            profiles = await self._uow.profiles.get_many_by_ids([cmd.winner_id, cmd.loser_id])
            winner = next((p for p in profiles if getattr(p, "id", None) == cmd.winner_id), None)
            loser = next((p for p in profiles if getattr(p, "id", None) == cmd.loser_id), None)

            if not winner or not loser:
                raise NotFoundError("Perfil no encontrado")

            if not getattr(winner, "is_active", False) or not getattr(winner, "is_approved", False):
                raise ValidationAppError("El perfil ganador no está disponible para votar")
            if not getattr(loser, "is_active", False) or not getattr(loser, "is_approved", False):
                raise ValidationAppError("El perfil perdedor no está disponible para votar")

            if cmd.voter_id is not None:
                exists = await self._uow.votes.exists_for_pair(
                    voter_id=cmd.voter_id, a_id=cmd.winner_id, b_id=cmd.loser_id
                )
                if exists:
                    raise ConflictError("Ya has votado en este emparejamiento")

            result = calculate_elo(winner_rating=winner.elo_score, loser_rating=loser.elo_score, k_factor=32)
            winner.elo_score = result.winner_rating
            winner.win_count += 1
            winner.voted_count += 1
            loser.elo_score = result.loser_rating
            loser.voted_count += 1

            vote = Vote(winner_id=cmd.winner_id, loser_id=cmd.loser_id, voter_id=cmd.voter_id)
            await self._uow.votes.add(vote)
            try:
                await self._uow.commit()
            except IntegrityError as exc:
                # Dos requests concurrentes intentaron registrar el mismo
                # emparejamiento (el check previo pasó en ambos). La BD impide
                # el duplicado; lo tratamos como un conflicto de negocio.
                logger.info(
                    "Voto duplicado rechazado (race) voter=%s winner=%s loser=%s",
                    cmd.voter_id, cmd.winner_id, cmd.loser_id,
                )
                raise ConflictError("Ya has votado en este emparejamiento") from exc
            await self._uow.votes.refresh(vote)

        if self._ranking_cache is not None:
            self._ranking_cache.invalidate()

        return vote
