import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.core.redis_client import redis_client
from app.db.session import engine

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

# Configurar todos los orígenes habilitados para CORS
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
else:
    # Alternativa para permitir todo en desarrollo si no se establecen orígenes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    logger.info("startup.begin")

    db_ok = False
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("startup.postgres.error", extra={"error": str(exc)})

    redis_ok = False
    if redis_client:
        try:
            redis_ok = bool(redis_client.ping())
        except Exception as exc:
            logger.error("startup.redis.error", extra={"error": str(exc)})

    logger.info(
        "startup.ready",
        extra={
            "postgres_ok": db_ok,
            "redis_ok": redis_ok,
        },
    )

@app.get("/")
async def root():
    return {"message": "Bienvenido a la API de Carómetro", "docs": "/docs"}

@app.get("/health")
async def health_check():
    db_ok = False
    db_error = None
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)

    redis_ok = None
    redis_error = None
    if redis_client is not None:
        redis_ok = False
        try:
            redis_ok = bool(redis_client.ping())
        except Exception as exc:
            redis_error = str(exc)

    overall_ok = db_ok and (redis_ok is None or redis_ok)
    return {
        "status": "healthy" if overall_ok else "degraded",
        "postgres": {"ok": db_ok, "error": db_error},
        "redis": {"ok": redis_ok, "error": redis_error},
    }
