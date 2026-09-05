import logging
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.ENV in ("production", "prod"):
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

app.add_middleware(GZipMiddleware, minimum_size=1024)

origins = settings.BACKEND_CORS_ORIGINS
is_prod = settings.ENV in ("production", "prod")

# Seguridad CORS: nunca combinar "*" con credenciales, y exigir orígenes
# explícitos en producción (fail-fast en lugar de abrir "*" silenciosamente).
if is_prod and not origins:
    raise RuntimeError(
        "BACKEND_CORS_ORIGINS debe configurarse en producción (no se permite '*')."
    )

if origins:
    allow_origins = origins
    allow_credentials = True
else:
    # Solo desarrollo: "*" sin credenciales (inseguro combinarlo con cookies).
    allow_origins = ["*"]
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SecurityHeadersMiddleware)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.on_event("startup")
async def startup_event():
    logger.info("Inicializando servidor...")

    db_ok = False
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: engine.connect().execute(text("SELECT 1")))
        db_ok = True
    except Exception as exc:
        logger.error("Falha na conexão com PostgreSQL", extra={"error": str(exc)})

    redis_ok = False
    redis_backend = "none"
    if redis_client:
        redis_backend = "in-memory" if not getattr(redis_client, "is_prod_backend", True) else "redis"
        try:
            redis_ok = bool(redis_client.ping())
        except Exception as exc:
            logger.error("Falha na conexão com Redis", extra={"error": str(exc)})

    logger.info(
        "Servidor pronto",
        extra={
            "postgres_ok": db_ok,
            "redis_ok": redis_ok,
            "redis_backend": redis_backend,
        },
    )


@app.get("/")
async def root():
    return {"message": "YoUprefer API", "docs": "/docs"}


def _check_db_sync() -> tuple[bool, str | None]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, None
    except Exception as exc:
        return False, str(exc)


@app.get("/health")
async def health_check():
    loop = asyncio.get_event_loop()
    db_ok, db_error = await loop.run_in_executor(None, _check_db_sync)

    redis_ok = None
    redis_error = None
    redis_backend = "none"
    if redis_client is not None:
        redis_ok = False
        redis_backend = "in-memory" if not getattr(redis_client, "is_prod_backend", True) else "redis"
        try:
            redis_ok = bool(redis_client.ping())
        except Exception as exc:
            redis_error = str(exc)

    overall_ok = db_ok and (redis_ok is None or redis_ok)
    return {
        "status": "healthy" if overall_ok else "degraded",
        "postgres": {"ok": db_ok, "error": db_error},
        "redis": {"ok": redis_ok, "error": redis_error, "backend": redis_backend},
    }
