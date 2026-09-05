"""Pruebas unitarias del módulo anti brute-force (app.core.lockout)."""

import pytest

from app.core.config import settings
from app.core import lockout


class FakeRedis:
    def __init__(self):
        self._data: dict[str, str] = {}
        self._ttl: dict[str, int] = {}

    def incr(self, key: str) -> int:
        current = int(self._data.get(key, "0")) + 1
        self._data[key] = str(current)
        return current

    def expire(self, key: str, seconds: int):
        self._ttl[key] = int(seconds)
        return True

    def setex(self, key: str, seconds: int, value: str):
        self._data[key] = str(value)
        self._ttl[key] = int(seconds)

    def ttl(self, key: str) -> int:
        return self._ttl.get(key, -2)

    def delete(self, key: str):
        self._data.pop(key, None)
        self._ttl.pop(key, None)


def _patch(monkeypatch, redis_obj):
    monkeypatch.setattr(lockout, "redis_client", redis_obj)
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_BASE_SECONDS", 60)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_MAX_SECONDS", 600)


def test_identity_normaliza_email_e_ip():
    assert lockout._identity("  User@Example.COM ", "1.2.3.4") == "user@example.com:1.2.3.4"
    assert lockout._identity("a@b.c", None) == "a@b.c:unknown"


def test_por_debajo_del_umbral_no_bloquea(monkeypatch):
    r = FakeRedis()
    _patch(monkeypatch, r)
    ident = "a@b.c:1.1.1.1"

    assert lockout.register_failed_attempt(ident) == 0
    assert lockout.register_failed_attempt(ident) == 0
    assert lockout.get_lockout_seconds(ident) == 0


def test_alcanza_umbral_y_aplica_bloqueo(monkeypatch):
    r = FakeRedis()
    _patch(monkeypatch, r)
    ident = "a@b.c:1.1.1.1"

    lockout.register_failed_attempt(ident)
    lockout.register_failed_attempt(ident)

    # Tercer fallo alcanza el umbral (MAX_ATTEMPTS=3).
    penalty = lockout.register_failed_attempt(ident)
    assert penalty > 0
    assert lockout.get_lockout_seconds(ident) > 0


def test_backoff_exponencial(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(lockout, "redis_client", r)
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_BASE_SECONDS", 60)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_MAX_SECONDS", 1000)
    ident = "a@b.c:1.1.1.1"

    lockout.register_failed_attempt(ident)
    p1 = lockout.register_failed_attempt(ident)  # 1º bloqueo: 60s
    p2 = lockout.register_failed_attempt(ident)  # 2º bloqueo: 120s
    p3 = lockout.register_failed_attempt(ident)  # 3º bloqueo: 240s

    assert p1 == 60
    assert p2 == 120
    assert p3 == 240


def test_backoff_respeto_tope_maximo(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(lockout, "redis_client", r)
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_BASE_SECONDS", 100)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_MAX_SECONDS", 250)
    ident = "a@b.c:1.1.1.1"

    p1 = lockout.register_failed_attempt(ident)  # 100s
    p2 = lockout.register_failed_attempt(ident)  # 200s
    p3 = lockout.register_failed_attempt(ident)  # ~400s -> cap 250s

    assert p1 == 100
    assert p2 == 200
    assert p3 == 250


def test_clear_lockout_restablece(monkeypatch):
    r = FakeRedis()
    _patch(monkeypatch, r)
    ident = "a@b.c:1.1.1.1"

    for _ in range(3):
        lockout.register_failed_attempt(ident)
    assert lockout.get_lockout_seconds(ident) > 0

    lockout.clear_lockout(ident)
    assert lockout.get_lockout_seconds(ident) == 0
    # Un nuevo fallo reinicia el contador desde 1 (sin bloqueo).
    assert lockout.register_failed_attempt(ident) == 0


def test_max_attempts_cero_desactiva_bloqueo(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(lockout, "redis_client", r)
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 0)
    ident = "a@b.c:1.1.1.1"

    assert lockout.register_failed_attempt(ident) == 0
    assert lockout.get_lockout_seconds(ident) == 0


def test_sin_redis_no_bloquea(monkeypatch):
    monkeypatch.setattr(lockout, "redis_client", None)
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    ident = "a@b.c:1.1.1.1"

    for _ in range(10):
        assert lockout.register_failed_attempt(ident) == 0
    assert lockout.get_lockout_seconds(ident) == 0
    lockout.clear_lockout(ident)  # no debe lanzar
