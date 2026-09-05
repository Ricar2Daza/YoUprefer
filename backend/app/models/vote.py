from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base_class import Base

class Vote(Base):
    __table_args__ = (
        # Garantiza a nivel de BD que un mismo usuario no registre dos veces el
        # mismo emparejamiento orientado (winner/loser), cerrando la carrera de
        # "select-then-insert" bajo concurrencia.
        UniqueConstraint("voter_id", "winner_id", "loser_id", name="uq_vote_voter_winner_loser"),
    )
    id = Column(Integer, primary_key=True, index=True)
    winner_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    loser_id = Column(Integer, ForeignKey("profile.id"), nullable=False, index=True)
    voter_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
