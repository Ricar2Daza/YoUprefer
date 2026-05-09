from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


class UserBlock(Base):
    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    blocker = relationship("User", foreign_keys=[blocker_id], back_populates="blocks_outgoing")
    blocked = relationship("User", foreign_keys=[blocked_id], back_populates="blocks_incoming")

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_user_block"),
    )

