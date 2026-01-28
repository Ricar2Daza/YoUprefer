from app.services.season_service import season_service
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.core import security

def test_ranking_reset_and_badges(db):
    # 1. Create a user and profiles
    user = User(email="winner@example.com", hashed_password=security.get_password_hash("pass"))
    db.add(user)
    db.commit()
    
    p1 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.MALE, elo_score=1500, is_approved=True, image_url="http://test.com/1.jpg")
    p2 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.FEMALE, elo_score=1400, is_approved=True, image_url="http://test.com/2.jpg")
    p3 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.MALE, elo_score=1300, is_approved=True, image_url="http://test.com/3.jpg")
    p4 = Profile(user_id=user.id, type=ProfileType.REAL, gender=Gender.FEMALE, elo_score=1000, is_approved=True, image_url="http://test.com/4.jpg")
    
    db.add_all([p1, p2, p3, p4])
    db.commit()
    
    # 2. Run reset
    season_service.reset_rankings_and_award_badges(db, "Test Season")
    
    # 3. Verify
    db.refresh(p1)
    db.refresh(p2)
    db.refresh(p3)
    db.refresh(p4)
    
    assert p1.elo_score == 1200
    assert p2.elo_score == 1200
    assert p3.elo_score == 1200
    assert p4.elo_score == 1200
    
    # Check if badges were awarded
    from app.models.badge import UserBadge
    badges = db.query(UserBadge).filter(UserBadge.user_id == user.id).all()
    assert len(badges) == 3 # Top 1, 2 and 3 belong to same user in this test
