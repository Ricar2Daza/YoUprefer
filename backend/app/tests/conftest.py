import os
import sys
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from httpx import AsyncClient, ASGITransport

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db.base import Base
from app.api.deps import get_async_db, get_db
from app.main import app

# URLs de conexión a la base de datos de prueba
# Por defecto usa SQLite para que pytest funcione sin Postgres/asyncpg.
# Si quieres Postgres, define TEST_DATABASE_URL y ASYNC_TEST_DATABASE_URL.
SQLALCHEMY_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./carometro_test.db")
ASYNC_SQLALCHEMY_DATABASE_URL = os.getenv("ASYNC_TEST_DATABASE_URL", "sqlite+aiosqlite:///./carometro_test.db")

is_sqlite_sync = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
sync_connect_args = {"check_same_thread": False} if is_sqlite_sync else {}

# Motor Síncrono (para endpoints que usan get_db)
engine_sync = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=sync_connect_args)
TestingSessionLocalSync = sessionmaker(autocommit=False, autoflush=False, bind=engine_sync)

@pytest.fixture(scope="session")
async def db_engine():
    """
    Crea el motor de base de datos asíncrono ligado al loop de la sesión.
    Usamos NullPool para evitar problemas de loop con conexiones en pool.
    """
    is_sqlite_async = ASYNC_SQLALCHEMY_DATABASE_URL.startswith("sqlite")
    async_connect_args = {"check_same_thread": False} if is_sqlite_async else {}

    engine = create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
        connect_args=async_connect_args,
    )
    yield engine
    await engine.dispose()

@pytest.fixture(scope="session")
async def db_session_factory(db_engine):
    """
    Factory de sesiones asíncronas.
    """
    return sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

@pytest.fixture(scope="session", autouse=True)
async def setup_db(db_engine):
    """
    Crea las tablas al inicio de la sesión de pruebas y las elimina al final.
    """
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db(db_session_factory) -> AsyncGenerator[AsyncSession, None]:
    """
    Proporciona una sesión de base de datos asíncrona para cada prueba.
    """
    async with db_session_factory() as session:
        yield session

@pytest.fixture
def db_sync() -> Generator[Session, None, None]:
    """
    Proporciona una sesión de base de datos síncrona para cada prueba.
    """
    session = TestingSessionLocalSync()
    try:
        yield session
    finally:
        session.close()

@pytest.fixture
async def client(db: AsyncSession, db_sync: Session) -> AsyncGenerator[AsyncClient, None]:
    """
    Proporciona un cliente HTTP asíncrono con las dependencias de base de datos (síncrona y asíncrona) sobrescritas.
    """
    async def override_get_async_db():
        yield db

    def override_get_db():
        yield db_sync
    
    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_db] = override_get_db
    
    # Usar ASGITransport para conectar directamente a la app FastAPI
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear()
