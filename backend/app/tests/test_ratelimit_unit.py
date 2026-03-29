import pytest
import fakeredis
from jose import jwt

from app.core.config import settings
from app.core.ratelimit import RateLimiter


class DummyUrl:
    def __init__(self, path: str):
        self.path = path


class DummyClient:
    def __init__(self, host: str):
        self.host = host


class DummyRequest:
    def __init__(self, path: str, host: str = "127.0.0.1", headers: dict | None = None):
        self.url = DummyUrl(path)
        self.client = DummyClient(host)
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_ratelimiter_blocks_after_limit(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.core.ratelimit.redis_client", r)

    limiter = RateLimiter(times=2, seconds=60)
    req = DummyRequest("/api/v1/votes/")

    await limiter(req)
    await limiter(req)

    with pytest.raises(Exception) as exc:
        await limiter(req)

    assert getattr(exc.value, "status_code", None) == 429


@pytest.mark.asyncio
async def test_ratelimiter_uses_user_id_when_bearer_token_present(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.core.ratelimit.redis_client", r)

    token = jwt.encode({"sub": "99"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    limiter = RateLimiter(times=1, seconds=60)
    req = DummyRequest("/api/v1/votes/", headers={"Authorization": f"Bearer {token}"})

    await limiter(req)

    keys = list(r.scan_iter("rate_limit:*"))
    assert any("user:99" in k for k in keys)

