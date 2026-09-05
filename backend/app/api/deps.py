import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app import models, schemas
from app.core.config import settings
from app.db.session import get_db, get_async_db
from app.core.redis_client import redis_client

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token")


def _is_token_blacklisted(jti: Optional[str]) -> bool:
    """Revocación coherente: la blacklist se indexa por 'jti', no por el JWT entero."""
    if not redis_client or not jti:
        return False
    try:
        return bool(redis_client.get(f"token:blacklist:{jti}"))
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Erro ao verificar blacklist no Redis", extra={"error": str(exc)})
        return False


def _decode_and_validate_token(token: str, expected_type: str = "access") -> schemas.TokenPayload:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )

    # Validación de issuer: el token debe haber sido emitido por esta API.
    if payload.get("iss") != settings.JWT_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Emisor de token inválido",
        )

    if _is_token_blacklisted(payload.get("jti")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token revocado"
        )

    if token_data.type and token_data.type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tipo de token inválido",
        )

    return token_data


def _check_user_active(user: models.User) -> None:
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")


def _check_user_banned(user: models.User) -> None:
    if user.is_banned and (user.banned_until is None or user.banned_until > datetime.now(timezone.utc)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario restringido",
        )


def _mark_online(user_id: int) -> None:
    if redis_client:
        try:
            redis_client.setex(f"online:{user_id}", 120, "1")
        except Exception as exc:
            logger.warning("Erro ao marcar usuário como online", extra={"user_id": user_id, "error": str(exc)})


def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    token_data = _decode_and_validate_token(token, expected_type="access")
    user = db.query(models.User).filter(models.User.id == token_data.sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _check_user_banned(user)
    _mark_online(user.id)
    return user


async def get_current_user_async(
    db: AsyncSession = Depends(get_async_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    token_data = _decode_and_validate_token(token, expected_type="access")
    result = await db.execute(select(models.User).filter(models.User.id == token_data.sub))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    _check_user_banned(user)
    _mark_online(user.id)
    return user


_oauth2_optional = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token",
    auto_error=False,
)


def get_current_user_optional(
    db: Session = Depends(get_db), token: str = Depends(_oauth2_optional)
) -> Optional[models.User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
    if payload.get("iss") != settings.JWT_ISSUER:
        return None
    user = db.query(models.User).filter(models.User.id == token_data.sub).first()
    return user


async def get_current_user_optional_async(
    db: AsyncSession = Depends(get_async_db), token: str = Depends(_oauth2_optional)
) -> Optional[models.User]:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
    if payload.get("iss") != settings.JWT_ISSUER:
        return None
    result = await db.execute(select(models.User).filter(models.User.id == token_data.sub))
    user = result.scalars().first()
    return user


def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    _check_user_active(current_user)
    return current_user


async def get_current_active_user_async(
    current_user: models.User = Depends(get_current_user_async),
) -> models.User:
    _check_user_active(current_user)
    return current_user


def get_current_active_superuser(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=400, detail="El usuario no tiene suficientes privilegios"
        )
    return current_user


async def get_current_active_superuser_async(
    current_user: models.User = Depends(get_current_user_async),
) -> models.User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=400, detail="El usuario no tiene suficientes privilegios"
        )
    return current_user
