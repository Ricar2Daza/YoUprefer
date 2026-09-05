"""Anti brute-force para login con bloqueo de backoff exponencial.

El bloqueo se identifica por email (en minúsculas) + IP, de modo que un
atacante no puede impedir el login de una víctima (el email no se puede
"quemar" desde otra IP) ni adivinar contraseñas por fuerza bruta desde una
misma IP. Utiliza Redis; con el fallback in-memory el contador se pierde al
reiniciar el proceso (aceptable en dev/prod con Redis real).

No se revela si el email existe: el contador crece indistintamente de si la
credencial es correcta y nunca se devuelve esa información.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import settings
from app.core.redis_client import redis_client

_ATTEMPTS_PREFIX = "login_attempts:"
_LOCK_PREFIX = "login_lock:"


def _identity(email: str, ip: str) -> str:
    return f"{email.strip().lower()}:{ip or 'unknown'}"


def get_lockout_seconds(identity: str) -> int:
    """Devuelve los segundos restantes de bloqueo, o 0 si no hay bloqueo."""
    if not settings.LOGIN_MAX_ATTEMPTS:
        return 0
    if redis_client is None:
        return 0
    ttl = redis_client.ttl(f"{_LOCK_PREFIX}{identity}")
    return max(0, int(ttl))


def register_failed_attempt(identity: str) -> int:
    """Registra un intento fallido y devuelve los segundos de bloqueo activos
    (0 si aún no se alcanzó el umbral)."""
    if not settings.LOGIN_MAX_ATTEMPTS or redis_client is None:
        return 0

    attempt_key = f"{_ATTEMPTS_PREFIX}{identity}"
    attempts = redis_client.incr(attempt_key)

    if attempts < settings.LOGIN_MAX_ATTEMPTS:
        redis_client.expire(attempt_key, settings.LOGIN_LOCKOUT_MAX_SECONDS)
        return 0

    over = attempts - settings.LOGIN_MAX_ATTEMPTS
    base = settings.LOGIN_LOCKOUT_BASE_SECONDS
    cap = settings.LOGIN_LOCKOUT_MAX_SECONDS
    penalty = min(base * (2**over), cap)

    redis_client.setex(f"{_LOCK_PREFIX}{identity}", penalty, "1")
    return penalty


def clear_lockout(identity: str) -> None:
    """Borra el contador y el bloqueo (login correcto)."""
    if redis_client is None:
        return
    redis_client.delete(f"{_ATTEMPTS_PREFIX}{identity}")
    redis_client.delete(f"{_LOCK_PREFIX}{identity}")
