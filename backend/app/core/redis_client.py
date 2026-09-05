from __future__ import annotations

import asyncio
import fnmatch
import logging
import time
from dataclasses import dataclass
from typing import Any

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


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


class _InMemoryPubSub:
    def __init__(self, parent: "_InMemoryRedis"):
        self._parent = parent
        self._channels: list[str] = []
        self._queues: list[asyncio.Queue[str]] = []

    def subscribe(self, channel: str) -> None:
        queue = self._parent._channel_queue(channel)
        self._channels.append(channel)
        self._queues.append(queue)

    def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 1.0):
        # Poll no bloqueante: nunca usar time.sleep aquí porque se invoca desde
        # handlers async (event loop); el backoff lo hace el llamado (asyncio.sleep).
        for q in self._queues:
            try:
                msg = q.get_nowait()
            except asyncio.QueueEmpty:
                continue
            return {"type": "message", "data": msg}
        return None

    def close(self) -> None:
        return None


class _InMemoryRedis:
    # Flag para distinguir el fallback en-memoria del Redis real en /health.
    is_prod_backend: bool = False

    def __init__(self):
        self._data: dict[str, _Entry] = {}
        self._channels: dict[str, asyncio.Queue[str]] = {}

    def _now(self) -> float:
        return time.time()

    def ping(self) -> bool:
        # El fallback en-memoria siempre responde OK (es funcionalmente sano).
        return True

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

    def _channel_queue(self, channel: str) -> asyncio.Queue[str]:
        queue = self._channels.get(channel)
        if queue is None:
            queue = asyncio.Queue(maxsize=1024)
            self._channels[channel] = queue
        return queue

    def get(self, key: str) -> str | None:
        entry = self._get_entry(key)
        return None if entry is None else entry.value

    def setex(self, key: str, seconds: int, value: str) -> None:
        self._data[key] = _Entry(value=str(value), expires_at=self._now() + int(seconds))

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        # Comportamiento compatible con redis-py: con nx=True solo setea si no existe.
        if nx and key in self._data and not self._is_expired(self._data[key]):
            return False
        self._data[key] = _Entry(value=str(value), expires_at=self._now() + ex if ex else None)
        return True

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

    def ttl(self, key: str) -> int:
        # Compatible con redis-py: >=0 segundos restantes, -1 sin expiración,
        # -2 si la clave no existe.
        entry = self._get_entry(key)
        if entry is None:
            return -2
        if entry.expires_at is None:
            return -1
        return max(0, int(entry.expires_at - self._now()))

    def publish(self, channel: str, message: str) -> int:
        queue = self._channel_queue(channel)
        try:
            queue.put_nowait(message)
            return 1
        except asyncio.QueueFull:
            return 0

    def pubsub(self) -> _InMemoryPubSub:
        return _InMemoryPubSub(self)


def _build_redis_client():
    client = redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=5,
    )
    client.ping()
    return client


try:
    redis_client = _build_redis_client()
    logger.info("Conexão com Redis estabelecida")
except Exception as exc:
    logger.warning("Redis não disponível, usando fallback in-memory", extra={"error": str(exc)})
    redis_client = _InMemoryRedis()
