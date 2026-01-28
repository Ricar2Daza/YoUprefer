import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.profile import Profile

def init_categories(db: Session):
    # Check if General category exists
    general = db.query(Category).filter(Category.slug == "general").first()
    if not general:
        print("Creating 'General' category...")
        general = Category(
            name="General",
            slug="general",
            description="Categoría general para todos los perfiles",
            is_active=True
        )
        db.add(general)
        db.commit()
        db.refresh(general)
    else:
        print("'General' category already exists.")

    # Assign all profiles with null category to General
    profiles = db.query(Profile).filter(Profile.category_id == None).all()
    count = 0
    for p in profiles:
        p.category_id = general.id
        count += 1
    
    if count > 0:
        db.commit()
        print(f"Assigned {count} profiles to 'General' category.")
    else:
        print("No profiles needed category assignment.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        init_categories(db)
    finally:
        db.close()
