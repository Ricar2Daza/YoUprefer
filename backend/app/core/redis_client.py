from __future__ import annotations

import fnmatch
import time
from dataclasses import dataclass
from typing import Any

import redis

from app.core.config import settings


@dataclass(slots=True)
class _Entry:
    value: str
    expires_at: float | None


class _Pipeline:
    def __init__(self, parent: "_InMemoryRedis"):
        self._parent = parent
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    def incr(self, key: str):
        self._ops.append(("incr", (key,)))
        return self

    def expire(self, key: str, seconds: int):
        self._ops.append(("expire", (key, seconds)))
        return self

    def execute(self):
        for name, args in self._ops:
            getattr(self._parent, name)(*args)
        self._ops.clear()


class _InMemoryRedis:
    def __init__(self):
        self._data: dict[str, _Entry] = {}

    def _now(self) -> float:
        return time.time()

    def _is_expired(self, entry: _Entry) -> bool:
        return entry.expires_at is not None and entry.expires_at <= self._now()

    def _get_entry(self, key: str) -> _Entry | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if self._is_expired(entry):
            self._data.pop(key, None)
            return None
        return entry

    def get(self, key: str) -> str | None:
        entry = self._get_entry(key)
        return None if entry is None else entry.value

    def setex(self, key: str, seconds: int, value: str) -> None:
        self._data[key] = _Entry(value=str(value), expires_at=self._now() + int(seconds))

    def delete(self, *keys: str) -> int:
        deleted = 0
        for k in keys:
            if k in self._data:
                self._data.pop(k, None)
                deleted += 1
        return deleted

    def scan_iter(self, match: str):
        for key in list(self._data.keys()):
            if self._get_entry(key) is None:
                continue
            if fnmatch.fnmatch(key, match):
                yield key

    def pipeline(self) -> _Pipeline:
        return _Pipeline(self)

    def incr(self, key: str) -> int:
        existing = self._get_entry(key)
        current = None if existing is None else existing.value
        next_val = int(current) + 1 if current is not None else 1
        self._data[key] = _Entry(value=str(next_val), expires_at=None if existing is None else existing.expires_at)
        return next_val

    def expire(self, key: str, seconds: int) -> bool:
        entry = self._get_entry(key)
        if entry is None:
            return False
        entry.expires_at = self._now() + int(seconds)
        return True


def _build_redis_client():
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=0.1,
        socket_timeout=0.2,
    )
    client.ping()
    return client


try:
    redis_client = _build_redis_client()
except Exception:
    redis_client = _InMemoryRedis()
