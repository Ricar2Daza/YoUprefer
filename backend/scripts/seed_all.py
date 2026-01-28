import sys
import os
import random

# Add parent directory to path to import app correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.core import security

def seed_data():
    db = SessionLocal()
    try:
        # 1. Create a demo user if not exists
        demo_user = db.query(User).filter(User.email == "demo@example.com").first()
        if not demo_user:
            demo_user = User(
                email="demo@example.com",
                hashed_password=security.get_password_hash("carometro2024"),
                full_name="Demo User",
                is_active=True
            )
            db.add(demo_user)
            db.commit()
            db.refresh(demo_user)
        
        # 2. Add some "REAL" profiles
        if db.query(Profile).filter(Profile.type == ProfileType.REAL).count() == 0:
            print("Seeding REAL profiles...")
            real_images_female = [
                "https://images.unsplash.com/photo-1544005313-94ddf0286df2",
                "https://images.unsplash.com/photo-1494790108377-be9c29b29330",
                "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04",
                "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91"
            ]
            for img in real_images_female:
                db.add(Profile(
                    type=ProfileType.REAL,
                    gender=Gender.FEMALE,
                    image_url=img,
                    elo_score=random.randint(1100, 1300),
                    user_id=demo_user.id,
                    is_approved=True,
                    is_active=True
                ))
            print("Seeding REAL profiles done.")

        # 3. Add AI profiles (if not already there)
        if db.query(Profile).filter(Profile.type == ProfileType.AI).count() == 0:
            print("Seeding AI profiles...")
            ai_images = [
                "https://images.unsplash.com/photo-1675865261317-0986797a7e0c", # Generic AI style
                "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe",
                "https://images.unsplash.com/photo-1620641788421-7a1c342ea42e"
            ]
            for img in ai_images:
                db.add(Profile(
                    type=ProfileType.AI,
                    gender=Gender.FEMALE,
                    image_url=img,
                    elo_score=random.randint(1200, 1400),
                    is_approved=True,
                    is_active=True
                ))
            print("Seeding AI profiles done.")
        
        db.commit()
    except Exception as e:
        print(f"Error seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
