from datetime import timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from jose import jwt
from pydantic import ValidationError
import httpx
from app import schemas, models
from app.api import deps
from app.core import security
from app.core.config import settings
from app.core.redis_client import redis_client

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
    
    # Simulación de envío de correo
    print(f"DEBUG: Password reset token for {email}: {password_reset_token}")
    
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
    except (jwt.JWTError, ValidationError):
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

@router.post("/google", response_model=schemas.Token)
async def login_google_oauth(
    req: schemas.SocialLoginRequest,
    db: Session = Depends(deps.get_db)
) -> Any:
    """
    Validar y loguear mediante el ID Token de Google (OAuth 2.0).
    """
    token = req.token
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={token}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Token de Google inválido o expirado"
            )
        token_info = response.json()
        
    email = token_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Token no contiene un correo electrónico")
        
    user = db.query(models.User).filter(models.User.email == email).first()
    
    if not user:
        # Registrar como nuevo
        user = models.User(
            email=email,
            full_name=token_info.get("name", "Usuario Google"),
            hashed_password=security.get_password_hash(token), # Dummy / Random
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
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
