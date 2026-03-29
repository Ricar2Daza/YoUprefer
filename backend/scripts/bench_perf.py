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
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import app
from app.core.config import settings
from app.core.redis_client import redis_client
from app.db.base import Base
from app.api.deps import get_async_db, get_db
from app.models.user import User
from app.models.category import Category
from app.models.profile import Profile, ProfileType, Gender

async def setup_data(db: AsyncSession):
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    user = User(email="bench@example.com", hashed_password="x", full_name="Bench", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    for i in range(300):
        p = Profile(
            user_id=user.id,
            category_id=category.id,
            type=ProfileType.REAL,
            gender=Gender.FEMALE,
            elo_score=1200 + (i % 200),
            is_approved=True,
            is_active=True,
            image_url=f"http://example.com/{i}.jpg"
        )
        db.add(p)
    await db.commit()

async def bench():
    SQLALCHEMY_DATABASE_URL = "sqlite:///./carometro_bench.db"
    ASYNC_SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./carometro_bench.db"
    engine_sync = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocalSync = sessionmaker(autocommit=False, autoflush=False, bind=engine_sync)
    engine_async = create_async_engine(ASYNC_SQLALCHEMY_DATABASE_URL, echo=False, poolclass=NullPool, connect_args={"check_same_thread": False})
    async_session_factory = sessionmaker(engine_async, class_=AsyncSession, expire_on_commit=False)
    async with engine_async.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as db:
        await setup_data(db)
    def override_get_db():
        session = TestingSessionLocalSync()
        try:
            yield session
        finally:
            session.close()
    async def override_get_async_db():
        async with async_session_factory() as session:
            yield session
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_async_db] = override_get_async_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if redis_client:
            try:
                for key in redis_client.scan_iter("ranking:*"):
                    redis_client.delete(key)
                for key in redis_client.scan_iter("pair_candidates:*"):
                    redis_client.delete(key)
            except Exception:
                pass
        t0 = time.perf_counter()
        r1 = await client.get(f"{settings.API_V1_STR}/profiles/ranking?limit=100", headers={"Accept-Encoding": "gzip"})
        t1 = time.perf_counter()
        r2 = await client.get(f"{settings.API_V1_STR}/profiles/ranking?limit=100", headers={"Accept-Encoding": "gzip"})
        t2 = time.perf_counter()
        p0 = time.perf_counter()
        rp1 = await client.get(f"{settings.API_V1_STR}/profiles/pair?gender=female")
        p1 = time.perf_counter()
        rp2 = await client.get(f"{settings.API_V1_STR}/profiles/pair?gender=female")
        p2 = time.perf_counter()
        print("ranking_first_ms", round((t1 - t0) * 1000, 2))
        print("ranking_second_ms", round((t2 - t1) * 1000, 2))
        print("ranking_encoding", r2.headers.get("Content-Encoding"))
        print("pair_first_ms", round((p1 - p0) * 1000, 2))
        print("pair_second_ms", round((p2 - p1) * 1000, 2))
    app.dependency_overrides.clear()

if __name__ == "__main__":
    asyncio.run(bench())
