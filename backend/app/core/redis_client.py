import redis
import fakeredis
from app.core.config import settings

# Crear cliente redis
# Usar try-except para manejar casos donde redis podría no estar disponible
try:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=1 # Fast fail
    )
    redis_client.ping()
    print("✅ Conectado a Redis real")
except:
    print("⚠️ Redis (real) no encontrado. Usando FakeRedis en memoria.")
    redis_client = fakeredis.FakeRedis(decode_responses=True)
