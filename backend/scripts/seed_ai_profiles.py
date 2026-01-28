import sys
import os
import random

# Add parent directory to path to import app correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.profile import Profile, ProfileType, Gender

def seed_ai_profiles():
    db = SessionLocal()
    try:
        # Check if already seeded
        if db.query(Profile).filter(Profile.type == ProfileType.AI).count() > 0:
            print("AI Profiles already existing. Skipping...")
            return

        print("Seeding AI Profiles...")
        
        # Mock URLs for testing
        ai_images_female = [
            "https://images.unsplash.com/photo-1494790108377-be9c29b29330",
            "https://images.unsplash.com/photo-1534528741775-53994a69daeb",
            "https://images.unsplash.com/photo-1544005313-94ddf0286df2",
            "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d"
        ]
        
        ai_images_male = [
            "https://images.unsplash.com/photo-1500648767791-00dcc994a43e",
            "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d",
            "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6",
            "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce"
        ]

        for i in range(10):
            gender = Gender.FEMALE if i % 2 == 0 else Gender.MALE
            images_list = ai_images_female if gender == Gender.FEMALE else ai_images_male
            
            profile = Profile(
                type=ProfileType.AI,
                gender=gender,
                image_url=random.choice(images_list),
                elo_score=random.randint(1100, 1300),
                is_approved=True,
                is_active=True
            )
            db.add(profile)
        
        db.commit()
        print("Successfully seeded 10 AI profiles!")
    except Exception as e:
        print(f"Error seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_ai_profiles()
