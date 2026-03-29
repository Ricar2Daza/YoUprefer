import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.season_service import season_service
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.models.badge import UserBadge
from app.core import security
from sqlalchemy.future import select

@pytest.mark.asyncio
async def test_ranking_reset_and_badges(db: AsyncSession):
    # 1. Create a user and profiles
    user = User(email="winner@example.com", hashed_password=security.get_password_hash("pass"))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    p1 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.MALE, elo_score=1500, is_approved=True, image_url="http://test.com/1.jpg")
    p2 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.FEMALE, elo_score=1400, is_approved=True, image_url="http://test.com/2.jpg")
    p3 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.MALE, elo_score=1300, is_approved=True, image_url="http://test.com/3.jpg")
    p4 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.FEMALE, elo_score=1000, is_approved=True, image_url="http://test.com/4.jpg")
    
    db.add_all([p1, p2, p3, p4])
    await db.commit()
    
    # 2. Run reset (Async)
    await season_service.async_reset_rankings_and_award_badges(db, "Test Season")
    
    # 3. Verify
    await db.refresh(p1)
    await db.refresh(p2)
    await db.refresh(p3)
    await db.refresh(p4)
    
    assert p1.elo_score == 1200
    assert p2.elo_score == 1200
    assert p3.elo_score == 1200
    assert p4.elo_score == 1200
    
    # Check if badges were awarded
    result = await db.execute(select(UserBadge).filter(UserBadge.user_id == user.id))
    badges = result.scalars().all()
    # La lógica de servicio puede otorgar hasta 3 insignias para el top global.
    # Verificamos que al menos una insignia haya sido asignada al usuario ganador.
    assert len(badges) >= 1
