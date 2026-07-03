from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from pydantic import ValidationError
import uuid
import httpx
from app import schemas, models
from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.redis_client import redis_client
from app.core.moderation import validate_text

router = APIRouter()

@router.post("/login/access-token", response_model=schemas.Token)
async def login_access_token(
    db: Session = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    Inicio de sesión compatible con OAuth2, obtener un token de acceso para futuras solicitudes
    """
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Correo o contraseña incorrectos")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "refresh_token": security.create_refresh_token(
            user.id, expires_delta=refresh_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/refresh-token", response_model=schemas.Token)
async def refresh_token(
    req: schemas.RefreshTokenRequest,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Refrescar token de acceso
    """
    try:
        # Validar blacklist en Redis antes de decodificar
        if redis_client:
            try:
                if redis_client.get(f"token:blacklist:{req.refresh_token}"):
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token revocado")
            except Exception:
                pass

        payload = jwt.decode(
            req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_data = schemas.TokenPayload(**payload)
        
        if token_data.type and token_data.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tipo de token inválido",
            )
    except (jwt.JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )
    
    user = db.query(models.User).filter(models.User.id == token_data.sub).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "refresh_token": security.create_refresh_token(
            user.id, expires_delta=refresh_token_expires
        ),
        "token_type": "bearer",
    }

@router.post("/logout", response_model=schemas.Msg)
async def logout(
    req: schemas.RefreshTokenRequest,
) -> Any:
    """
    Logout: revocar refresh token para evitar nuevos accesos.
    Opcionalmente, los access tokens activos expiran pronto; se puede colocar también en blacklist si se desea.
    """
    try:
        if redis_client:
            try:
                # Calcular expiración restante del token para usarla como TTL
                payload = jwt.decode(req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                exp = payload.get("exp")
                ttl = max(int(exp - (__import__("time").time())), 1) if exp else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                redis_client.setex(f"token:blacklist:{req.refresh_token}", ttl, "1")
            except Exception:
                # Si hay error con Redis o decode, continuar sin bloquear
                pass
        return {"msg": "Sesión cerrada correctamente"}
    except Exception:
        return {"msg": "Sesión cerrada"}


@router.post("/register", response_model=schemas.User)
async def register_user(
    *,
    db: Session = Depends(deps.get_db),
    user_in: schemas.UserCreate,
) -> Any:
    """
    Crear nuevo usuario.
    """
    existing = db.query(models.User).filter(models.User.email == user_in.email).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="El usuario con este correo ya existe en el sistema.",
        )
    
    user = models.User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/oauth/google", response_model=schemas.Token)
async def oauth_google(
    req: schemas.OAuthTokenRequest,
    db: Session = Depends(deps.get_db),
) -> Any:
    token = (req.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token inválido")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": token})
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="No se pudo validar el token de Google")

    data = r.json()
    email = data.get("email")
    name = data.get("name") or data.get("given_name") or ""
    if not email:
        raise HTTPException(status_code=400, detail="Google no devolvió email")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        try:
            validate_text(name, fields=("nombre",))
        except ValueError:
            name = ""
        user = models.User(
            email=email,
            hashed_password=security.get_password_hash(str(uuid.uuid4())),
            full_name=name,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return {
        "access_token": security.create_access_token(user.id, expires_delta=access_token_expires),
        "refresh_token": security.create_refresh_token(user.id, expires_delta=refresh_token_expires),
        "token_type": "bearer",
    }


@router.post("/oauth/facebook", response_model=schemas.Token)
async def oauth_facebook(
    req: schemas.OAuthTokenRequest,
    db: Session = Depends(deps.get_db),
) -> Any:
    token = (req.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token inválido")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email", "access_token": token},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="No se pudo validar el token de Facebook")

    data = r.json()
    email = data.get("email")
    name = data.get("name") or ""
    if not email:
        raise HTTPException(status_code=400, detail="Facebook no devolvió email")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        try:
            validate_text(name, fields=("nombre",))
        except ValueError:
            name = ""
        user = models.User(
            email=email,
            hashed_password=security.get_password_hash(str(uuid.uuid4())),
            full_name=name,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return {
        "access_token": security.create_access_token(user.id, expires_delta=access_token_expires),
        "refresh_token": security.create_refresh_token(user.id, expires_delta=refresh_token_expires),
        "token_type": "bearer",
    }

@router.post("/password-recovery/{email}", response_model=schemas.Msg)
async def recover_password(email: str, db: Session = Depends(deps.get_db)) -> Any:
    """
    Recuperación de contraseña
    """
    user = db.query(models.User).filter(models.User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="El usuario con este correo no existe en el sistema.",
        )
    
    # En una aplicación real, generarías un token y enviarías un correo aquí.
    # Por ahora, simulamos el flujo.
    password_reset_token = security.create_access_token(
        subject=user.email, expires_delta=timedelta(hours=1)
    )

    return {"msg": "Correo de recuperación de contraseña enviado"}

@router.post("/reset-password/", response_model=schemas.Msg)
async def reset_password(
    token: str,
    new_password: str,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Restablecer contraseña
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        email = payload.get("sub")
    except (JWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )
    
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="El usuario con este correo no existe en el sistema.",
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    
    user.hashed_password = security.get_password_hash(new_password)
    db.add(user)
    db.commit()
    return {"msg": "Contraseña actualizada exitosamente"}
