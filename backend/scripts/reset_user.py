import asyncio
import sys
import os

# Add the parent directory to sys.path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.profile import Profile, ProfileType, Gender
from app.core.security import get_password_hash

async def reset_users():
    print("Conectando a la base de datos...")
    async with AsyncSessionLocal() as session:
        try:
            print("Eliminando usuarios y perfiles existentes...")
            await session.execute(delete(Profile))
            await session.execute(delete(User))
            await session.commit()
            
            # 1. Create Admin User
            email = "rikadaza11@hotmail.com"
            password = "prueba"
            hashed = get_password_hash(password)
            
            print(f"Creando usuario admin: {email}")
            admin_user = User(
                email=email,
                hashed_password=hashed,
                full_name="Usuario Prueba",
                is_active=True,
                is_superuser=True
            )
            session.add(admin_user)
            
            # 2. Create Seed Users with Profiles (so there is something to vote on)
            print("Creando usuarios candidatos para votar...")

            test_password = "test123"
            hashed_test = get_password_hash(test_password)

            candidates = [
                {"email": "ana@test.com", "name": "Ana Test", "img": "https://images.unsplash.com/photo-1544005313-94ddf0286df2"},
                {"email": "sofia@test.com", "name": "Sofia Test", "img": "https://images.unsplash.com/photo-1494790108377-be9c29b29330"},
                {"email": "lucia@test.com", "name": "Lucia Test", "img": "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04"},
                {"email": "maria@test.com", "name": "Maria Test", "img": "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91"}
            ]

            test_users = [
                {"email": "test1@test.com", "name": "Test 1", "img": "https://images.unsplash.com/photo-1544005313-94ddf0286df2"},
                {"email": "test2@test.com", "name": "Test 2", "img": "https://images.unsplash.com/photo-1494790108377-be9c29b29330"},
                {"email": "test3@test.com", "name": "Test 3", "img": "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91"},
                {"email": "test4@test.com", "name": "Test 4", "img": "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04"},
                {"email": "test5@test.com", "name": "Test 5", "img": "https://images.unsplash.com/photo-1544005313-94ddf0286df2"}
            ]

            for c in candidates:
                user = User(
                    email=c["email"],
                    hashed_password=hashed,
                    full_name=c["name"],
                    is_active=True
                )
                session.add(user)
                await session.flush()

                profile = Profile(
                    type=ProfileType.REAL,
                    gender=Gender.FEMALE,
                    image_url=c["img"],
                    elo_score=1200,
                    user_id=user.id,
                    is_approved=True,
                    is_active=True,
                    legal_consent=True
                )
                session.add(profile)

            for t in test_users:
                user = User(
                    email=t["email"],
                    hashed_password=hashed_test,
                    full_name=t["name"],
                    is_active=True
                )
                session.add(user)
                await session.flush()

                profile = Profile(
                    type=ProfileType.REAL,
                    gender=Gender.FEMALE,
                    image_url=t["img"],
                    elo_score=1200,
                    user_id=user.id,
                    is_approved=True,
                    is_active=True,
                    legal_consent=True
                )
                session.add(profile)

            test_password = "test123"
            hashed_test = get_password_hash(test_password)

            print("Creando usuarios de prueba...")
            test_users = [
                {"email": "test1@test.com", "name": "Test 1", "img": "https://images.unsplash.com/photo-1544005313-94ddf0286df2"},
                {"email": "test2@test.com", "name": "Test 2", "img": "https://images.unsplash.com/photo-1494790108377-be9c29b29330"},
                {"email": "test3@test.com", "name": "Test 3", "img": "https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91"},
                {"email": "test4@test.com", "name": "Test 4", "img": "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04"},
                {"email": "test5@test.com", "name": "Test 5", "img": "https://images.unsplash.com/photo-1544005313-94ddf0286df2"}
            ]

            for t in test_users:
                user = User(
                    email=t["email"],
                    hashed_password=hashed_test,
                    full_name=t["name"],
                    is_active=True
                )
                session.add(user)
                await session.flush()

                profile = Profile(
                    type=ProfileType.REAL,
                    gender=Gender.FEMALE,
                    image_url=t["img"],
                    elo_score=1200,
                    user_id=user.id,
                    is_approved=True,
                    is_active=True,
                    legal_consent=True
                )
                session.add(profile)

            await session.commit()
            print(f"Base de datos reseteada exitosamente.")
            print(f"Admin: {email} / {password}")
            print(f"Candidatos creados: {len(candidates)}")
            print(f"Usuarios test creados: {len(test_users)}")
            print(f"Password test: {test_password}")
            print(f"Usuarios test creados: {len(test_users)}")
            print(f"Credenciales test: test1@test.com .. test{len(test_users)}@test.com / {test_password}")
            
        except Exception as e:
            print(f"Error: {e}")
            await session.rollback()

if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            from asyncio import WindowsProactorEventLoopPolicy
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
        except ImportError:
            pass  # Not on Windows or policy not available
    asyncio.run(reset_users())
