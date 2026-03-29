from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.db.base_class import Base

class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"

class ProfileType(enum.Enum):
    REAL = "real"
    AI = "ai"

class Profile(Base):
    id = Column(Integer, primary_key=True, index=True)
    type = Column(Enum(ProfileType), nullable=False, index=True)
    gender = Column(Enum(Gender), nullable=False, index=True)
    image_url = Column(String, nullable=False)
    elo_score = Column(Integer, default=1200)
    voted_count = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    
    # Enlace de usuario para personas reales
    user_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    owner = relationship("User", back_populates="profiles")
    
    # Enlace de Categoría/Tema
    category_id = Column(Integer, ForeignKey("category.id"), nullable=True, index=True)
    category = relationship("Category", back_populates="profiles")

    is_active = Column(Boolean, default=True, index=True)
    is_approved = Column(Boolean, default=False, index=True)
    
    # Aspectos legales
    legal_consent = Column(Boolean, default=False)
    legal_consent_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
