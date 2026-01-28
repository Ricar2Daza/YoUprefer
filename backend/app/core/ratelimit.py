import redis
import fakeredis
from app.core.config import settings
from fastapi import HTTPException, Request, status
import time

# Create redis client
# Using a try-except to handle cases where redis might not be available
try:
    redis_client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=1 # Fast fail
    )
    redis_client.ping()
    print("✅ Connected to real Redis")
except:
    print("⚠️ Redis (real) not found. Using InMemory FakeRedis.")
    redis_client = fakeredis.FakeRedis(decode_responses=True)

def RateLimiter(times: int, seconds: int):
    """
    Simple Rate Limiter dependency using Redis.
    Allows 'times' requests per 'seconds'.
    """
    async def wrapper(request: Request):
        if not redis_client:
            return  # Skip if redis is not available

        # Get client identifier (IP or User ID)
        # For authenticated routes, you might want to use current_user.id
        client_id = request.client.host
        
        # Unique key for this endpoint and client
        key = f"rate_limit:{request.url.path}:{client_id}"
        
        try:
            current = redis_client.get(key)
            
            if current and int(current) >= times:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many requests. Limit is {times} per {seconds} seconds."
                )
            
            # Increment and set expiry if new
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, seconds)
            pipe.execute()
            
        except redis.RedisError:
            # Fallback: if redis fails, let the request through
            pass
            
    return wrapper
