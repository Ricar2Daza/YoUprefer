import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.profile import Profile

def init_categories(db: Session):
    # Verificar si existe la categoría General
    general = db.query(Category).filter(Category.slug == "general").first()
    if not general:
        print("Creando categoría 'General'...")
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
        print("La categoría 'General' ya existe.")

    # Asignar todos los perfiles sin categoría a General
    profiles = db.query(Profile).filter(Profile.category_id == None).all()
    count = 0
    for p in profiles:
        p.category_id = general.id
        count += 1
    
    if count > 0:
        db.commit()
        print(f"Asignados {count} perfiles a la categoría 'General'.")
    else:
        print("Ningún perfil necesitó asignación de categoría.")

if __name__ == "__main__":
    db = SessionLocal()
    try:
        init_categories(db)
    finally:
        db.close()
