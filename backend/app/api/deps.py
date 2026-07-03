from datetime import datetime, timezone
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

reusable_oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token")

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    try:
        # Verificar blacklist
        if redis_client:
            try:
                if redis_client.get(f"token:blacklist:{token}"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Token revocado"
                    )
            except Exception:
                pass
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
        
        if token_data.type and token_data.type != "access":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tipo de token inválido",
            )
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )
    user = db.query(models.User).filter(models.User.id == token_data.sub).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.is_banned and (user.banned_until is None or user.banned_until > datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario restringido")
    if redis_client:
        try:
            redis_client.setex(f"online:{user.id}", 120, "1")
        except Exception:
            pass
    return user

async def get_current_user_async(
    db: AsyncSession = Depends(get_async_db), token: str = Depends(reusable_oauth2)
) -> models.User:
    try:
        if redis_client:
            try:
                if redis_client.get(f"token:blacklist:{token}"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Token revocado"
                    )
            except Exception:
                pass
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
        
        if token_data.type and token_data.type != "access":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tipo de token inválido",
            )
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )
    # Async query
    result = await db.execute(select(models.User).filter(models.User.id == token_data.sub))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.is_banned and (user.banned_until is None or user.banned_until > datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario restringido")
    if redis_client:
        try:
            redis_client.setex(f"online:{user.id}", 120, "1")
        except Exception:
            pass
    return user

def get_current_user_optional(
    db: Session = Depends(get_db), token: str = Depends(OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token", auto_error=False))
) -> models.User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
        
    user = db.query(models.User).filter(models.User.id == token_data.sub).first()
    return user

async def get_current_user_optional_async(
    db: AsyncSession = Depends(get_async_db), token: str = Depends(OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login/access-token", auto_error=False))
) -> models.User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
    except (JWTError, ValidationError):
        return None
        
    result = await db.execute(select(models.User).filter(models.User.id == token_data.sub))
    user = result.scalars().first()
    return user



def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

async def get_current_active_user_async(
    current_user: models.User = Depends(get_current_user_async),
) -> models.User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
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
