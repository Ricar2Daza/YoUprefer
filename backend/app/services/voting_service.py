from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from app.models.profile import Profile
from app.models.vote import Vote
from app.services.ranking_service import ranking_service

class VotingService:
    @staticmethod
    async def record_vote(db: AsyncSession, winner_id: int, loser_id: int, voter_id: int = None):
        # Fetch both profiles in a single query
        result = await db.execute(select(Profile).filter(Profile.id.in_([winner_id, loser_id])))
        profiles = result.scalars().all()
        
        winner = next((p for p in profiles if p.id == winner_id), None)
        loser = next((p for p in profiles if p.id == loser_id), None)

        if not winner or not loser:
            raise ValueError("Perfil no encontrado")

        # Verificar que ambos perfiles estén activos y aprobados
        if not winner.is_active or not winner.is_approved:
            raise ValueError(f"El perfil ganador no está disponible para votar")
        if not loser.is_active or not loser.is_approved:
            raise ValueError(f"El perfil perdedor no está disponible para votar")

        # Verificar si el usuario ya votó por este par (en cualquier dirección)
        if voter_id:
            result_vote = await db.execute(select(Vote).filter(
                Vote.voter_id == voter_id,
                or_(
                    (Vote.winner_id == winner_id) & (Vote.loser_id == loser_id),
                    (Vote.winner_id == loser_id) & (Vote.loser_id == winner_id)
                )
            ))
            existing_vote = result_vote.scalars().first()
            
            if existing_vote:
                raise ValueError("Ya has votado en este emparejamiento")

        # Calcular nuevos puntajes ELO
        new_winner_rating, new_loser_rating = ranking_service.calculate_elo(
            winner.elo_score, loser.elo_score
        )

        # Actualizar perfiles
        winner.elo_score = new_winner_rating
        winner.win_count += 1
        winner.voted_count += 1
        
        loser.elo_score = new_loser_rating
        loser.voted_count += 1

        # Registrar voto
        vote = Vote(
            winner_id=winner_id,
            loser_id=loser_id,
            voter_id=voter_id
        )
        db.add(vote)
        await db.commit()
        await db.refresh(vote)
        return vote

voting_service = VotingService()

