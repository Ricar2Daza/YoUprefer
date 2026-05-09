from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base


class CustomVote(Base):
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("category.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    expiring_notified = Column(Boolean, default=False)

    owner = relationship("User", foreign_keys=[owner_id], back_populates="custom_votes_created")
    category = relationship("Category")
    participants = relationship("CustomVoteParticipant", back_populates="vote", cascade="all, delete-orphan")
    ballots = relationship("CustomVoteBallot", back_populates="vote", cascade="all, delete-orphan")


class CustomVoteParticipant(Base):
    id = Column(Integer, primary_key=True, index=True)
    vote_id = Column(Integer, ForeignKey("customvote.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    vote = relationship("CustomVote", back_populates="participants")
    user = relationship("User")
    photos = relationship("CustomVotePhoto", back_populates="participant", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("vote_id", "user_id", name="uq_custom_vote_participant"),
    )


class CustomVotePhoto(Base):
    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("customvoteparticipant.id"), nullable=False, index=True)
    image_url = Column(String, nullable=False)
    object_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    participant = relationship("CustomVoteParticipant", back_populates="photos")


class CustomVoteBallot(Base):
    id = Column(Integer, primary_key=True, index=True)
    vote_id = Column(Integer, ForeignKey("customvote.id"), nullable=False, index=True)
    voter_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    photo_id = Column(Integer, ForeignKey("customvotephoto.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    vote = relationship("CustomVote", back_populates="ballots")
    voter = relationship("User")
    photo = relationship("CustomVotePhoto")

    __table_args__ = (
        UniqueConstraint("vote_id", "voter_id", name="uq_custom_vote_ballot"),
    )
