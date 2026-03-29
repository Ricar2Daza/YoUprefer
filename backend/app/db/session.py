from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Usar la URL de la base de datos desde la configuración
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL
if isinstance(SQLALCHEMY_DATABASE_URL, (bytes, bytearray)):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.decode("utf-8", errors="ignore")
SQLALCHEMY_DATABASE_URL = str(SQLALCHEMY_DATABASE_URL).strip().strip("\ufeff")

# Configurar URL asíncrona para PostgreSQL
base_url = SQLALCHEMY_DATABASE_URL.split("?", 1)[0]
ASYNC_SQLALCHEMY_DATABASE_URL = base_url.replace("postgresql://", "postgresql+asyncpg://")

# Motor Síncrono
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Motor Asíncrono
# Nota: create_async_engine intenta importar el driver (p.ej. asyncpg) en tiempo de importación.
# Para permitir que el proyecto (y los tests) arranque incluso si asyncpg no está instalado,
# creamos el motor de forma defensiva y fallamos con un error claro solo si se usa get_async_db.
async_engine = None
AsyncSessionLocal = None
try:
    async_engine = create_async_engine(
        ASYNC_SQLALCHEMY_DATABASE_URL,
        echo=False,
    )
    AsyncSessionLocal = sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
except ModuleNotFoundError:
    async_engine = None
    AsyncSessionLocal = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_async_db():
    if AsyncSessionLocal is None:
        raise RuntimeError(
            "Async DB driver no disponible. Instala 'asyncpg' para Postgres."
        )
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
