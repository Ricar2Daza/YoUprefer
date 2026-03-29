from app.core.config import settings
from fastapi import HTTPException, Request, status
from app.core.redis_client import redis_client
import time
import redis
from jose import jwt

def RateLimiter(times: int, seconds: int):
    """
    Dependencia simple de limitador de tasa usando Redis.
    Permite 'times' peticiones por 'seconds' segundos.
    """
    async def wrapper(request: Request):
        if not redis_client:
            return  # Omitir si redis no está disponible

        # Obtener identificador de cliente (IP o ID de usuario extraído del token)
        client_id = request.client.host
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            try:
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                sub = payload.get("sub")
                if sub is not None:
                    client_id = f"user:{sub}"
            except Exception:
                # Si el token no es válido, seguir usando la IP
                pass
        
        # Clave única para este endpoint y cliente
        key = f"rate_limit:{request.url.path}:{client_id}"
        
        try:
            current = redis_client.get(key)
            
            if current and int(current) >= times:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Demasiadas peticiones. El límite es {times} por {seconds} segundos."
                )
            
            # Incrementar y establecer expiración si es nuevo
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, seconds)
            pipe.execute()
            
        except redis.RedisError:
            # Fallback: si redis falla, dejar pasar la petición
            pass
            
    return wrapper
