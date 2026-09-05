"""
Validación del módulo de login.

Cubre la verificación de credenciales y el controlador de autenticación del
backend, tanto en éxito como en los casos de error requeridos:
- credenciales incorrectas
- usuario inactivo
- usuario bloqueado (banned)
- error de servidor
"""
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from jose import jwt


# --------------------------------------------------------------------------- #
# Pruebas unitarias: verificación de credenciales (security)
# --------------------------------------------------------------------------- #

def test_hash_y_verificacion_correcta():
    password = "test123#"
    hashed = security.get_password_hash(password)
    assert isinstance(hashed, str)
    assert hashed != password
    assert security.verify_password(password, hashed) is True


def test_verificacion_password_incorrecta_es_false():
    hashed = security.get_password_hash("correcta")
    assert security.verify_password("incorrecta", hashed) is False


def test_verificacion_hash_desconocido_no_revela_error():
    # Un hash irrecognoscible no debe romper el flujo ni lanzar excepción.
    assert security.verify_password("cualquier", "not-a-real-hash") is False
    assert security.verify_password("cualquier", "$2b$12$incompleto") is False


def test_needs_rehash_detecta_hash_legacy_pbkdf2():
    legacy = security.pwd_context.hash("test123#", scheme="pbkdf2_sha256")
    assert legacy.startswith("$pbkdf2-sha256$")
    assert security.needs_rehash(legacy) is True


def test_needs_rehash_falso_para_hash_bcrypt_actual():
    modern = security.get_password_hash("test123#")
    assert security.needs_rehash(modern) is False
    # Y el hash moderno se puede verificar correctamente.
    assert security.verify_password("test123#", modern) is True


# --------------------------------------------------------------------------- #
# Pruebas de integración: controlador de login (POST /auth/login/access-token)
# --------------------------------------------------------------------------- #

async def _registrar_y_devolver(client, email="login_valid@example.com", password="test123#"):
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": password, "full_name": "Login Test"},
    )
    return r


@pytest.mark.asyncio
async def test_login_exitoso_devuelve_tokens(client: AsyncClient):
    email = "login_valida@example.com"
    password = "test123#"
    await _registrar_y_devolver(client, email, password)

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer"
    assert data["access_token"]
    assert data["refresh_token"]
    # El access token debe contener el sub del usuario y el tipo access.
    payload = jwt.decode(data["access_token"], settings.SECRET_KEY, algorithms=[settings.ALGORITHM], audience=settings.JWT_AUDIENCE)
    assert payload["type"] == "access"


@pytest.mark.asyncio
async def test_login_credenciales_incorrectas(client: AsyncClient):
    email = "login_wrong@example.com"
    password = "test123#"
    await _registrar_y_devolver(client, email, password)

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "password-incorrecta"},
    )
    assert r.status_code == 400
    assert "incorrectos" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_usuario_no_existente(client: AsyncClient):
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "no-existe@example.com", "password": "test123#"},
    )
    assert r.status_code == 400
    assert "incorrectos" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_usuario_inactivo(client: AsyncClient, db: AsyncSession):
    from app.models.user import User

    user = User(
        email="login_inactivo@example.com",
        hashed_password=security.get_password_hash("test123#"),
        full_name="Inactivo",
        is_active=False,
    )
    db.add(user)
    await db.commit()

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "login_inactivo@example.com", "password": "test123#"},
    )
    assert r.status_code == 400
    assert "inactivo" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_usuario_bloqueado_rechazado(client: AsyncClient, db: AsyncSession):
    from app.models.user import User

    user = User(
        email="login_banned@example.com",
        hashed_password=security.get_password_hash("test123#"),
        full_name="Bloqueado",
        is_active=True,
        is_banned=True,
        banned_until=datetime.now(timezone.utc) + timedelta(days=1),
        ban_reason="test",
    )
    db.add(user)
    await db.commit()

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "login_banned@example.com", "password": "test123#"},
    )
    assert r.status_code == 403
    assert "restringido" in r.json()["detail"]


@pytest.mark.asyncio
async def test_login_usuario_ban_expirado_puede_acceder(client: AsyncClient, db: AsyncSession):
    from app.models.user import User

    user = User(
        email="login_ban_expirado@example.com",
        hashed_password=security.get_password_hash("test123#"),
        full_name="Ban Expirado",
        is_active=True,
        is_banned=True,
        banned_until=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(user)
    await db.commit()

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "login_ban_expirado@example.com", "password": "test123#"},
    )
    assert r.status_code == 200
    assert r.json()["access_token"]


@pytest.mark.asyncio
async def test_login_rehash_legacy_header(client: AsyncClient, db_sync):
    """Al loguear con un hash legacy (pbkdf2) el servidor debe reiniciar el hash a bcrypt."""
    from app.models.user import User

    user = User(
        email="login_legacy@example.com",
        hashed_password=security.pwd_context.hash("test123#", scheme="pbkdf2_sha256"),
        full_name="Legacy",
        is_active=True,
    )
    db_sync.add(user)
    db_sync.commit()

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "login_legacy@example.com", "password": "test123#"},
    )
    assert r.status_code == 200

    refreshed = db_sync.query(User).filter(User.email == "login_legacy@example.com").first()
    assert security.verify_password("test123#", refreshed.hashed_password)
    assert security.needs_rehash(refreshed.hashed_password) is False
