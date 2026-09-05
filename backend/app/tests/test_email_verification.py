import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.redis_client import redis_client
from app.models.user import User


@pytest.fixture(autouse=True)
def _email_settings():
    """Asegura un estado predecible de las settings de email entre tests."""
    prev_enabled = settings.EMAIL_ENABLED
    prev_provider = settings.EMAIL_PROVIDER
    yield
    settings.EMAIL_ENABLED = prev_enabled
    settings.EMAIL_PROVIDER = prev_provider


@pytest.fixture(autouse=True)
def _clean_verify_tokens():
    """Limpia tokens email_verify entre tests (backend real o in-memory)."""
    try:
        for key in list(redis_client.scan_iter("email_verify:*")):
            redis_client.delete(key)
    except Exception:
        pass
    yield


async def _register(client: AsyncClient, email: str) -> dict:
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "password123", "full_name": "Verif"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _get_user(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).filter(User.email == email))
    return result.scalars().first()


def _verify_tokens() -> list[str]:
    """Devuelve los tokens email_verify activos (backend real o in-memory)."""
    return [k.split(":", 1)[1] for k in redis_client.scan_iter("email_verify:*")]


@pytest.mark.asyncio
async def test_register_creates_token_and_unverified_user(client: AsyncClient, db: AsyncSession):
    user_data = await _register(client, "verify@example.com")
    assert user_data["email"] == "verify@example.com"
    assert user_data["is_email_verified"] is False

    tokens = _verify_tokens()
    assert len(tokens) == 1, "El registro debería haber creado un token de verificación"


@pytest.mark.asyncio
async def test_verify_email_marks_user_as_verified(client: AsyncClient, db: AsyncSession):
    await _register(client, "verify2@example.com")

    tokens = _verify_tokens()
    assert len(tokens) == 1
    token = tokens[0]

    r = await client.post(f"{settings.API_V1_STR}/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert "verificado" in r.json()["msg"].lower()

    user = await _get_user(db, "verify2@example.com")
    assert user is not None
    assert user.is_email_verified is True

    # El token se consume (un solo uso).
    assert _verify_tokens() == []


@pytest.mark.asyncio
async def test_verify_email_invalid_token(client: AsyncClient, db: AsyncSession):
    r = await client.post(f"{settings.API_V1_STR}/auth/verify-email", json={"token": "no-existe"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_verify_email_already_verified_idempotente(client: AsyncClient, db: AsyncSession):
    email = "verify3@example.com"
    await _register(client, email)

    # Marcamos manualmente el correo como verificado (simula un usuario que ya
    # completó el flujo) y reutilizamos un token viejo aún presente en Redis.
    user = await _get_user(db, email)
    assert user is not None
    user.is_email_verified = True
    await db.commit()

    tokens = _verify_tokens()
    assert tokens, "Debería existir un token"

    r = await client.post(f"{settings.API_V1_STR}/auth/verify-email", json={"token": tokens[0]})
    assert r.status_code == 200, r.text
    assert "ya estaba verificado" in r.json()["msg"].lower()


@pytest.mark.asyncio
async def test_verify_email_token_para_usuario_inexistente(client: AsyncClient, db: AsyncSession):
    token = uuid.uuid4().hex
    redis_client.setex(f"email_verify:{token}", 3600, "999999")

    r = await client.post(f"{settings.API_V1_STR}/auth/verify-email", json={"token": token})
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_resend_verification_genera_nuevo_token(client: AsyncClient, db: AsyncSession):
    email = "resend@example.com"
    await _register(client, email)
    assert len(_verify_tokens()) == 1

    r = await client.post(f"{settings.API_V1_STR}/auth/resend-verification", json={"email": email})
    assert r.status_code == 200, r.text
    assert "enviado" in r.json()["msg"].lower()

    # El reenvío crea un token nuevo.
    assert len(_verify_tokens()) == 2


@pytest.mark.asyncio
async def test_resend_verification_email_inexistente_no_revela(client: AsyncClient, db: AsyncSession):
    # No debe revelar si el correo existe: misma respuesta 200.
    r = await client.post(
        f"{settings.API_V1_STR}/auth/resend-verification",
        json={"email": "nadie@sistema.com"},
    )
    assert r.status_code == 200, r.text
    assert "enviado" in r.json()["msg"].lower()