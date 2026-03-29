import asyncio
import time
from httpx import AsyncClient
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.future import select
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
import sys, os

# Añadir el directorio backend al path
sys.path.insert(0, os.path.abspath('backend'))

from app.main import app
from app.core.config import settings
from app.core.redis_client import redis_client
from app.db.base import Base
from app.api.deps import get_async_db, get_db
from app.models.user import User
from app.models.category import Category
from app.models.profile import Profile
from app.models.vote import Vote

# Forzar SQLite para tests
settings.DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Crear BD de test
engine = create_engine("sqlite:///./test.db", poolclass=NullPool)
Base.metadata.create_all(bind=engine)

# Crear algunos datos de prueba
from sqlalchemy.orm import Session
with Session(engine) as session:
    # Crear usuario admin
    admin = User(
        email="admin@test.com",
        username="admin",
        full_name="Admin User",
        is_superuser=True,
        is_active=True
    )
    admin.set_password("test123")
    session.add(admin)
    
    # Crear categoría
    cat = Category(name="Test Category", description="Test")
    session.add(cat)
    session.commit()
    
    # Crear perfiles
    for i in range(10):
        profile = Profile(
            user_id=admin.id,
            category_id=cat.id,
            name=f"Profile {i}",
            description=f"Test profile {i}",
            gender="male" if i % 2 == 0 else "female",
            is_active=True,
            is_approved=True
        )
        session.add(profile)
    session.commit()

async def bench():
    print("🚀 Iniciando benchmark...")
    
    # Override de dependencias
    async def override_get_async_db():
        async_engine = create_async_engine("sqlite+aiosqlite:///./test.db", poolclass=NullPool)
        async_session = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            yield session
    
    app.dependency_overrides[get_async_db] = override_get_async_db
    
    # Benchmark
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Ranking endpoint
        t0 = time.perf_counter()
        r1 = await client.get(f"{settings.API_V1_STR}/profiles/ranking?limit=100")
        t1 = time.perf_counter()
        
        # Segunda llamada (con cache)
        r2 = await client.get(f"{settings.API_V1_STR}/profiles/ranking?limit=100", headers={"Accept-Encoding": "gzip"})
        t2 = time.perf_counter()
        
        # Pair endpoint
        p0 = time.perf_counter()
        rp1 = await client.get(f"{settings.API_V1_STR}/profiles/pair?gender=female")
        p1 = time.perf_counter()
        
        rp2 = await client.get(f"{settings.API_V1_STR}/profiles/pair?gender=female")
        p2 = time.perf_counter()
        
        print("=== RESULTADOS DEL BENCHMARK ===")
        print(f"ranking_first_ms: {round((t1 - t0) * 1000, 2)}")
        print(f"ranking_second_ms: {round((t2 - t1) * 1000, 2)}")
        print(f"ranking_encoding: {r2.headers.get('Content-Encoding', 'none')}")
        print(f"pair_first_ms: {round((p1 - p0) * 1000, 2)}")
        print(f"pair_second_ms: {round((p2 - p1) * 1000, 2)}")
        
        # Calcular mejoras
        ranking_improvement = round((1 - (t2 - t1)/(t1 - t0)) * 100, 1) if (t1 - t0) > 0 else 0
        pair_improvement = round((1 - (p2 - p1)/(p1 - p0)) * 100, 1) if (p1 - p0) > 0 else 0
        
        print(f"\n📊 MEJORAS DE RENDIMIENTO:")
        print(f"Ranking: {ranking_improvement}% de mejora (cache)")
        print(f"Pair: {pair_improvement}% de mejora (cache)")
        print(f"Compresion GZip: {'✓' if r2.headers.get('Content-Encoding') == 'gzip' else '✗'}")
    
    app.dependency_overrides.clear()
    print("✅ Benchmark completado!")

if __name__ == "__main__":
    asyncio.run(bench())