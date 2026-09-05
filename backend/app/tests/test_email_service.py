import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.email_service import (
    email_service,
    build_password_reset_url,
    build_email_verify_url,
)
from app.models.user import User
from app.core import security


@pytest.fixture(autouse=True)
def _email_settings():
    """Asegura un estado predecible de las settings de email entre tests."""
    prev_enabled = settings.EMAIL_ENABLED
    prev_provider = settings.EMAIL_PROVIDER
    prev_frontend = settings.FRONTEND_URL
    yield
    settings.EMAIL_ENABLED = prev_enabled
    settings.EMAIL_PROVIDER = prev_provider
    settings.FRONTEND_URL = prev_frontend


class TestUrls:
    def test_password_reset_url_incluye_token(self):
        url = build_password_reset_url("abc123")
        assert url.startswith("http://localhost:3000/reset-password")
        assert "token=abc123" in url

    def test_email_verify_url_incluye_token(self):
        url = build_email_verify_url("xyz")
        assert url.startswith("http://localhost:3000/verify-email")
        assert "token=xyz" in url

    def test_url_usa_frontend_configurado(self, monkeypatch):
        monkeypatch.setattr(settings, "FRONTEND_URL", "https://app.youprefer.com")
        url = build_password_reset_url("t")
        assert url.startswith("https://app.youprefer.com/reset-password")


class TestService:
    def test_modo_log_envia_y_devuelve_true(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "log")
        import logging
        with caplog.at_level(logging.INFO, logger="app.services.email_service"):
            ok = email_service.send_password_recovery_email("a@b.com", "tok1")
        assert ok is True
        assert "tok1" in caplog.text
        assert "reset-password" in caplog.text

    def test_modo_print_devuelve_true(self, monkeypatch, capsys):
        monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "print")
        ok = email_service.send_verification_email("a@b.com", "v1")
        assert ok is True
        captured = capsys.readouterr()
        assert "verify-email" in captured.out

    def test_email_disabled_no_envia(self, monkeypatch, caplog):
        monkeypatch.setattr(settings, "EMAIL_ENABLED", False)
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "log")
        import logging
        with caplog.at_level(logging.DEBUG, logger="app.services.email_service"):
            ok = email_service.send_password_recovery_email("a@b.com", "tok1")
        assert ok is False

    def test_smtp_sin_credenciales_falla_graceful(self, monkeypatch):
        monkeypatch.setattr(settings, "EMAIL_ENABLED", True)
        monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
        monkeypatch.setattr(settings, "SMTP_HOST", None)
        monkeypatch.setattr(settings, "SMTP_USER", None)
        monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
        # No debe lanzar excepción aunque no haya proveedor SMTP configurado.
        ok = email_service.send_password_recovery_email("a@b.com", "tok1")
        assert ok is False


@pytest.mark.asyncio
async def test_recover_password_genera_token_y_responde(client: AsyncClient, db):
    # Usa la sesión async (db) para crear el usuario y el cliente HTTP para
    # verificar el flujo completo de recovery (el envío es best-effort).
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.core.config import settings as s

    db = db if isinstance(db, AsyncSession) else db  # db ya es AsyncSession
    user = User(
        email="recover@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Recover",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Con EMAIL_ENABLED=False el servicio no envía, pero la respuesta sigue siendo
    # 200 y el mensaje esperado (el envío es best-effort).
    assert s.EMAIL_ENABLED is False
    r = await client.post(f"{s.API_V1_STR}/auth/password-recovery/recover@example.com")
    assert r.status_code == 200
    assert "Correo de recuperación" in r.json()["msg"]
