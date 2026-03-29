from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class Season(Base):
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

class Badge(Base):
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    icon = Column(String) # For example: '👑', '🔥', '💎'
    category = Column(String, index=True) # e.g., 'ranking', 'participation'
    level = Column(String) # e.g., 'bronce', 'plata', 'oro', 'platino'
    rarity = Column(String) # e.g., 'common', 'rare', 'epic', 'legendary'
    min_position = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)

class UserBadge(Base):
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), index=True)
    badge_id = Column(Integer, ForeignKey("badge.id"), index=True)
    profile_id = Column(Integer, ForeignKey("profile.id"), nullable=True)
    season_id = Column(Integer, ForeignKey("season.id"), index=True, nullable=True)
    awarded_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="badges")
    badge = relationship("Badge")
    season = relationship("Season")

    __table_args__ = (
        UniqueConstraint('user_id', 'badge_id', 'season_id', name='uq_user_badge_season'),
    )
