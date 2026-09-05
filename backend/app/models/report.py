from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

from app.db.base_class import Base


class ReportStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    APPEALED = "appealed"


class Report(Base):
    id = Column(Integer, primary_key=True, index=True)
    reporter_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    target_profile_id = Column(Integer, ForeignKey("profile.id"), nullable=True, index=True)
    target_user_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    target_comment_id = Column(Integer, ForeignKey("comment.id"), nullable=True, index=True)
    reason = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    status = Column(SAEnum(ReportStatus), nullable=False, default=ReportStatus.PENDING)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    appeal_reason = Column(String, nullable=True)
    appealed_at = Column(DateTime(timezone=True), nullable=True)

    reporter = relationship("User", foreign_keys=[reporter_id])
    target_profile = relationship("Profile", foreign_keys=[target_profile_id])
    target_user = relationship("User", foreign_keys=[target_user_id])
    target_comment = relationship("Comment", foreign_keys=[target_comment_id])

