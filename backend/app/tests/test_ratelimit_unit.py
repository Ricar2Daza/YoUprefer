import pytest
from jose import jwt
from typing import Optional, Dict

from app.core.config import settings
from app.core.ratelimit import RateLimiter


class FakeRedis:
    def __init__(self):
        self._data: dict[str, str] = {}

    def get(self, key: str):
        return self._data.get(key)

    def setex(self, key: str, _seconds: int, value: str):
        self._data[key] = str(value)

    def scan_iter(self, match: str):
        prefix = match.split("*", 1)[0]
        for k in list(self._data.keys()):
            if k.startswith(prefix):
                yield k

    def delete(self, key: str):
        self._data.pop(key, None)

    def incr(self, key: str):
        current = int(self._data.get(key, "0"))
        self._data[key] = str(current + 1)
        return current + 1

    def expire(self, _key: str, _seconds: int):
        return True

    def pipeline(self):
        parent = self

        class _Pipe:
            def __init__(self):
                self._ops: list[tuple[str, tuple]] = []

            def incr(self, key: str):
                self._ops.append(("incr", (key,)))
                return self

            def expire(self, key: str, seconds: int):
                self._ops.append(("expire", (key, seconds)))
                return self

            def execute(self):
                for name, args in self._ops:
                    getattr(parent, name)(*args)
                self._ops.clear()

        return _Pipe()


class DummyUrl:
    def __init__(self, path: str):
        self.path = path


class DummyClient:
    def __init__(self, host: str):
        self.host = host


class DummyRequest:
    def __init__(self, path: str, host: str = "127.0.0.1", headers: Optional[Dict] = None):
        self.url = DummyUrl(path)
        self.client = DummyClient(host)
        self.headers = headers or {}


@pytest.mark.asyncio
async def test_ratelimiter_blocks_after_limit(monkeypatch):
    r = FakeRedis()
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
    r = FakeRedis()
    monkeypatch.setattr("app.core.ratelimit.redis_client", r)

    token = jwt.encode({"sub": "99"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    limiter = RateLimiter(times=1, seconds=60)
    req = DummyRequest("/api/v1/votes/", headers={"Authorization": f"Bearer {token}"})

    await limiter(req)

    keys = list(r.scan_iter("rate_limit:*"))
    assert any("user:99" in k for k in keys)
