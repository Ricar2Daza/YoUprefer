import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import time
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
from app.core.ratelimit import RateLimiter
from app.core.lockout import (
    _identity,
    clear_lockout,
    get_lockout_seconds,
    register_failed_attempt,
)
from app.core.redis_client import redis_client
from app.core.moderation import validate_text
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter()

_GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
_FACEBOOK_DEBUG_TOKEN_URL = "https://graph.facebook.com/debug_token"


def _datetime_is_after_now(value) -> bool:
    """Compara de forma robusta una fecha (aware o naive) con el momento actual."""
    now = datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > now



def _refresh_blacklist_key(token_jti: str) -> str:
    return f"token:blacklist:{token_jti}"


def _refresh_used_key(family_id: str) -> str:
    return f"token:family:{family_id}"


def _revoke_family(family_id: str) -> None:
    if not redis_client or not family_id:
        return
    try:
        redis_client.setex(_refresh_used_key(family_id), 60 * 60 * 24 * 90, "revoked")
    except Exception as exc:
        logger.warning("Erro ao revogar família de tokens", extra={"family_id": family_id, "error": str(exc)})


def _is_family_revoked(family_id: str) -> bool:
    if not redis_client or not family_id:
        return False
    try:
        return bool(redis_client.get(_refresh_used_key(family_id)))
    except Exception as exc:
        logger.warning("Erro ao verificar família revogada", extra={"family_id": family_id, "error": str(exc)})
        return False


def _blacklist_jti(jti: str, ttl_seconds: int) -> None:
    if not redis_client or not jti:
        return
    try:
        redis_client.setex(f"token:blacklist:{jti}", max(ttl_seconds, 1), "1")
    except Exception as exc:
        logger.warning("Erro ao blacklistar jti", extra={"error": str(exc)})

@router.post(
    "/login/access-token",
    response_model=schemas.Token,
    dependencies=[Depends(RateLimiter(times=10, seconds=60))],
)
async def login_access_token(
    request: Request,
    db: Session = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> Any:
    """
    Inicio de sesión compatible con OAuth2, obtener un token de acceso para futuras solicitudes
    """
    ip = request.client.host if request.client else None
    identity = _identity(form_data.username, ip)

    locked_seconds = get_lockout_seconds(identity)
    if locked_seconds > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Intente de nuevo en {locked_seconds} segundos.",
        )

    user = db.query(models.User).filter(models.User.email == form_data.username).first()

    if not user or not security.verify_password(form_data.password, user.hashed_password):
        penalty = register_failed_attempt(identity)
        if penalty > 0:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos fallidos. Intente de nuevo en {penalty} segundos.",
            )
        raise HTTPException(status_code=400, detail="Correo o contraseña incorrectos")
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    if user.is_banned and (user.banned_until is None or _datetime_is_after_now(user.banned_until)):
        raise HTTPException(status_code=403, detail="Usuario restringido")

    clear_lockout(identity)

    if security.needs_rehash(user.hashed_password):
        user.hashed_password = security.get_password_hash(form_data.password)
        db.add(user)
        db.commit()
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    family_id = uuid.uuid4().hex
    return {
        "access_token": security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        "refresh_token": security.create_refresh_token(
            user.id, expires_delta=refresh_token_expires, family_id=family_id
        ),
        "token_type": "bearer",
    }

@router.post("/refresh-token", response_model=schemas.Token)
async def refresh_token(
    req: schemas.RefreshTokenRequest,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Refrescar token de acceso.

    Implementa rotación de refresh tokens con detección de reuso:
    - Cada refresh emite un nuevo par access+refresh, marca el jti presentado
      en blacklist y guarda el ``jti`` consumido en una "familia".
    - Si se vuelve a presentar un refresh cuyo jti ya está en blacklist, se
      asume compromiso y se invalida toda la familia.
    """
    try:
        payload = jwt.decode(
            req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
        token_data = schemas.TokenPayload(**payload)

        if token_data.type and token_data.type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tipo de token inválido",
            )

        jti = payload.get("jti")
        family_id = payload.get("fid")
        if not jti or not family_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Refresh token sin identificadores de rotación",
            )

        # Revocación por jti (coherente con la escritura de logout/refresh).
        if redis_client:
            try:
                if redis_client.get(f"token:blacklist:{jti}"):
                    _revoke_family(family_id)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Token revocado",
                    )
            except HTTPException:
                raise
            except Exception as exc:
                logger.warning("Erro ao verificar blacklist no Redis", extra={"error": str(exc)})

        # Detección de reuso: si la familia está revocada o el jti está en blacklist,
        # tratamos como compromiso y revocamos la familia entera.
        if _is_family_revoked(family_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Familia de tokens revocada por uso sospechoso",
            )

        used_key = f"refresh:used:{family_id}:{jti}"
        if redis_client:
            try:
                if redis_client.get(used_key):
                    _revoke_family(family_id)
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Refresh token reutilizado: familia revocada",
                    )
            except HTTPException:
                raise
            except Exception:
                logger.warning("Failed to validate refresh token family in Redis", exc_info=True)
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

    new_access = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    new_refresh = security.create_refresh_token(
        user.id, expires_delta=refresh_token_expires, family_id=family_id
    )

    # Marcar jti del refresh presentado como consumido (TTL = duración del nuevo refresh)
    if redis_client:
        try:
            redis_client.setex(used_key, settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60, "1")
        except Exception:
            logger.warning("Failed to mark refresh token as used in Redis", exc_info=True)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
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
                payload = jwt.decode(req.refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                exp = payload.get("exp")
                ttl = max(int(exp - time.time()), 1) if exp else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                jti = payload.get("jti")
                family_id = payload.get("fid")
                if jti:
                    _blacklist_jti(jti, ttl)
                if family_id:
                    _revoke_family(family_id)
            except Exception as exc:
                logger.warning("Erro ao processar logout no Redis", extra={"error": str(exc)})
        return {"msg": "Sesión cerrada correctamente"}
    except Exception as exc:
        logger.warning("Erro ao processar logout", extra={"error": str(exc)})
        return {"msg": "Sesión cerrada"}


@router.post(
    "/register",
    response_model=schemas.User,
    dependencies=[Depends(RateLimiter(times=10, seconds=3600))],
)
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
        is_email_verified=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Enviar correo de verificación de email (best-effort). El registro nunca
    # debe fallar por un problema de email: EMAIL_ENABLED=False (dev/tesis) no
    # envía nada; si el envío falla, el usuario puede re-solicitarlo vía
    # /auth/resend-verification.
    verification_token = uuid.uuid4().hex
    if redis_client:
        try:
            redis_client.setex(f"email_verify:{verification_token}", 3600, str(user.id))
        except Exception:
            logger.warning("Error al guardar token de verificación de email", exc_info=True)
    email_service.send_verification_email(user_in.email, verification_token)

    return user


@router.post("/oauth/google", response_model=schemas.Token)
async def oauth_google(
    req: schemas.OAuthTokenRequest,
    db: Session = Depends(deps.get_db),
) -> Any:
    token = (req.token or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token inválido")

    if not settings.GOOGLE_OAUTH_CLIENT_IDS:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth no está configurado en el servidor",
        )

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(_GOOGLE_TOKENINFO_URL, params={"id_token": token})
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="No se pudo validar el token de Google")

    data = r.json()

    if str(data.get("aud")) not in settings.GOOGLE_OAUTH_CLIENT_IDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Google emitido para otra aplicación",
        )

    if str(data.get("iss")) not in _GOOGLE_ISSUERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Emisor de token de Google no válido",
        )

    if str(data.get("email_verified")).lower() not in {"true", "1"}:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="El email de Google no está verificado",
        )

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
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    family_id = uuid.uuid4().hex
    return {
        "access_token": security.create_access_token(user.id, expires_delta=access_token_expires),
        "refresh_token": security.create_refresh_token(user.id, expires_delta=refresh_token_expires, family_id=family_id),
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

    if not settings.FACEBOOK_OAUTH_APP_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Facebook OAuth no está configurado en el servidor",
        )

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://graph.facebook.com/me",
            params={"fields": "id,name,email", "access_token": token},
        )
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail="No se pudo validar el token de Facebook")

    data = r.json()

    fb_id = data.get("id")
    if not fb_id:
        raise HTTPException(status_code=400, detail="Facebook no devolvió id de usuario")

    async with httpx.AsyncClient(timeout=10) as client:
        debug_r = await client.get(
            _FACEBOOK_DEBUG_TOKEN_URL,
            params={
                "input_token": token,
                "access_token": f"{settings.FACEBOOK_OAUTH_APP_ID}|{token}",
            },
        )
    if debug_r.status_code == 200:
        debug_data = debug_r.json().get("data", {})
        if not debug_data.get("is_valid"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de Facebook inválido",
            )
        if str(debug_data.get("app_id")) != str(settings.FACEBOOK_OAUTH_APP_ID):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de Facebook emitido para otra aplicación",
            )

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
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario inactivo")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    family_id = uuid.uuid4().hex
    return {
        "access_token": security.create_access_token(user.id, expires_delta=access_token_expires),
        "refresh_token": security.create_refresh_token(user.id, expires_delta=refresh_token_expires, family_id=family_id),
        "token_type": "bearer",
    }

@router.post("/ws-ticket", response_model=dict)
async def create_ws_ticket(
    current_user: models.User = Depends(deps.get_current_user_async),
):
    """
    Genera un ticket de curta duração (30s) para conexão WebSocket.
    Evita expor o JWT em query strings.
    """
    import secrets
    ticket = secrets.token_hex(16)
    if redis_client:
        try:
            redis_client.setex(f"ws_ticket:{ticket}", 30, str(current_user.id))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No fue posible generar el ticket.",
            )
    return {"ticket": ticket}


@router.post("/password-recovery/{email}", response_model=schemas.Msg)
async def recover_password(email: str, db: Session = Depends(deps.get_db)) -> Any:
    """
    Inicia el flujo de recuperación de contraseña.
    Genera un token de un solo uso, lo almacena en Redis y
    (en producción) enviaría un email con el enlace.
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="El usuario con este correo no existe en el sistema.",
        )

    reset_token = uuid.uuid4().hex
    ttl_seconds = 3600  # 1 hora
    if redis_client:
        try:
            redis_client.setex(f"password_reset:{reset_token}", ttl_seconds, str(user.id))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al generar token de recuperación. Intente nuevamente.",
            )

    logger.info(
        "password_recovery_token_generated",
        extra={"user_id": user.id, "token_ttl": ttl_seconds},
    )

    # Enviar correo de recuperación (best-effort). El servicio no lanza errores
    # hacia acá: si el envío falla o no hay proveedor configurado, el token ya
    # quedó registrado y la respuesta sigue siendo segura (no revela si el
    # correo existe más allá del flujo normal).
    email_service.send_password_recovery_email(email, reset_token)

    return {
        "msg": "Correo de recuperación de contraseña enviado",
    }


@router.post("/reset-password", response_model=schemas.Msg)
async def reset_password(
    body: schemas.ResetPassword,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Restablece la contraseña usando un token de recuperación.
    El token debe haberse obtenido via POST /password-recovery/{email}.
    """
    token = body.token.strip()
    new_password = body.new_password

    if not token or not new_password:
        raise HTTPException(status_code=400, detail="Token y nueva contraseña son requeridos.")

    if len(new_password) < 8:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 8 caracteres.")

    user_id_str = None
    if redis_client:
        try:
            user_id_str = redis_client.get(f"password_reset:{token}")
        except Exception:
            logger.warning("Failed to read password_reset token from Redis", exc_info=True)

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token inválido o expirado. Solicite un nuevo token de recuperación.",
        )

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Token inválido.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    user.hashed_password = security.get_password_hash(new_password)
    db.add(user)
    db.commit()

    if redis_client:
        try:
            redis_client.delete(f"password_reset:{token}")
        except Exception:
            logger.warning("Failed to delete password_reset token from Redis", exc_info=True)

    return {"msg": "Contraseña actualizada exitosamente."}


@router.post("/verify-email", response_model=schemas.Msg)
async def verify_email(
    body: schemas.VerifyEmail,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Verifica la dirección de correo de un usuario usando el token enviado por el
    servicio de email (POST /auth/register o POST /auth/resend-verification).
    Token de un solo uso con TTL de 1 hora.
    """
    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token requerido.")

    user_id_str = None
    if redis_client:
        try:
            user_id_str = redis_client.get(f"email_verify:{token}")
        except Exception:
            logger.warning("Failed to read email_verify token from Redis", exc_info=True)

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token de verificación inválido o expirado. Solicite uno nuevo.",
        )

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Token inválido.")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if user.is_email_verified:
        # El correo ya se verificó; consumimos el token de todos modos (idempotente).
        _consume_verify_token(token)
        return {"msg": "Tu correo ya estaba verificado."}

    user.is_email_verified = True
    db.add(user)
    db.commit()
    _consume_verify_token(token)

    return {"msg": "Correo verificado exitosamente."}


@router.post("/resend-verification", response_model=schemas.Msg)
async def resend_verification(
    body: schemas.ResendVerification,
    db: Session = Depends(deps.get_db),
) -> Any:
    """
    Reenvía el correo de verificación de email.
    Genera un token nuevo (el anterior queda invalidado) y lo envía (best-effort).
    """
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user:
        # No revelar si el correo existe; misma respuesta que un envío exitoso.
        return {"msg": "Correo de verificación enviado"}

    verification_token = uuid.uuid4().hex
    if redis_client:
        try:
            redis_client.setex(f"email_verify:{verification_token}", 3600, str(user.id))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error al generar token de verificación. Intente nuevamente.",
            )

    logger.info(
        "email_verification_token_generated",
        extra={"user_id": user.id, "token_ttl": 3600},
    )

    email_service.send_verification_email(body.email, verification_token)

    return {"msg": "Correo de verificación enviado"}


def _consume_verify_token(token: str) -> None:
    if not redis_client:
        return
    try:
        redis_client.delete(f"email_verify:{token}")
    except Exception:
        logger.warning("Failed to delete email_verify token from Redis", exc_info=True)
