from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class User(Base):
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    
    profiles = relationship("Profile", back_populates="owner", cascade="all, delete-orphan")
    badges = relationship("UserBadge", back_populates="user")
    votes_cast = relationship("Vote", backref="voter", lazy="dynamic")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def votes_cast_count(self):
        return self.votes_cast.count()
