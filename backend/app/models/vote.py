from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.db.base_class import Base

class Vote(Base):
    id = Column(Integer, primary_key=True, index=True)
    winner_id = Column(Integer, ForeignKey("profile.id"), nullable=False)
    loser_id = Column(Integer, ForeignKey("profile.id"), nullable=False)
    voter_id = Column(Integer, ForeignKey("user.id"), nullable=True) # Optional for visitors
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
