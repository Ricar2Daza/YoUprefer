from datetime import datetime, timedelta
from typing import Any, Union
import uuid
from jose import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt", "pbkdf2_sha256"],
    deprecated="auto",
)
from app.core.config import settings


def _is_legacy_hash(hashed: str) -> bool:
    return hashed.startswith("$pbkdf2-sha256$")


def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None, jti: str | None = None, **extra: Any) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "access",
        "jti": jti or uuid.uuid4().hex,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        **extra,
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(subject: Union[str, Any], expires_delta: timedelta = None, jti: str | None = None, family_id: str | None = None, **extra: Any) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=7)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "jti": jti or uuid.uuid4().hex,
        "fid": family_id or uuid.uuid4().hex,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        **extra,
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Hash que no se puede identificar (ej. "not-a-hash") o error interno
        # del backend no deben exponer la causa ni romper el flujo de login.
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def needs_rehash(hashed_password: str) -> bool:
    return _is_legacy_hash(hashed_password) or pwd_context.needs_update(hashed_password)