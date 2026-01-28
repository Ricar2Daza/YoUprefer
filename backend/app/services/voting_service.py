from sqlalchemy.orm import Session
from app.models.profile import Profile
from app.models.vote import Vote
from app.services.ranking_service import ranking_service

class VotingService:
    @staticmethod
    def record_vote(db: Session, winner_id: int, loser_id: int, voter_id: int = None):
        winner = db.query(Profile).filter(Profile.id == winner_id).first()
        loser = db.query(Profile).filter(Profile.id == loser_id).first()

        if not winner or not loser:
            raise ValueError("Profile not found")

        # Calculate new ELO scores
        new_winner_rating, new_loser_rating = ranking_service.calculate_elo(
            winner.elo_score, loser.elo_score
        )

        # Update profiles
        winner.elo_score = new_winner_rating
        winner.win_count += 1
        winner.voted_count += 1
        
        loser.elo_score = new_loser_rating
        loser.voted_count += 1

        # Record vote
        vote = Vote(
            winner_id=winner_id,
            loser_id=loser_id,
            voter_id=voter_id
        )
        db.add(vote)
        db.commit()
        db.refresh(vote)
        return vote

voting_service = VotingService()
