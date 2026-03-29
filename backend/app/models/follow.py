from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.db.base_class import Base


class Follow(Base):
    id = Column(Integer, primary_key=True, index=True)
    follower_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    following_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("follower_id", "following_id", name="uq_user_follow"),
    )

