import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.profile import Profile, ProfileType, Gender
from app.core.config import settings


@pytest.mark.asyncio
async def test_participation_status_without_profiles(client: AsyncClient):
    # Registrar usuario
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": "noprof@example.com", "password": "pass123", "full_name": "No Prof"},
    )
    assert r.status_code == 200
    user = r.json()
    # Login
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "noprof@example.com", "password": "pass123"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    # Consultar estado
    r = await client.get(
        f"{settings.API_V1_STR}/profiles/me/participation-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["participating"] is False
    assert data["can_upload"] is True
    assert data["active_profile_id"] is None


@pytest.mark.asyncio
async def test_upload_direct_creates_active_and_blocks_second_upload(client: AsyncClient):
    # Registrar y login
    email = "uploaddir@example.com"
    await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "pass123", "full_name": "Uploader"},
    )
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "pass123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Subida directa (simular con mínima carga multipart usando bytes pequeños)
    # Nota: con httpx+ASGITransport, enviar multipart requiere files=; aquí usamos endpoint que acepta FormData.
    
    # Activar directamente el perfil (simular aprobación) con upload_direct: crea aprobado
    files = {"file": ("photo.jpg", b"fake-binary", "image/jpeg")}
    data = {"gender": "female", "legal_consent": "true"}
    with patch("app.services.storage.storage_service.upload_file", return_value=True):
        r = await client.post(f"{settings.API_V1_STR}/profiles/upload-direct", headers=headers, files=files, data=data)
    assert r.status_code == 200
    created = r.json()
    assert created["is_approved"] is True

    # Estado debe indicar participación
    r = await client.get(
        f"{settings.API_V1_STR}/profiles/me/participation-status",
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["participating"] is True
    assert data["can_upload"] is False
    assert isinstance(data["active_profile_id"], int)

    # Intentar otra creación debe fallar (create_profile)
    r = await client.post(
        f"{settings.API_V1_STR}/profiles/",
        headers=headers,
        json={"gender": "female", "legal_consent": True},
    )
    assert r.status_code == 400
    assert "Ya tienes un perfil activo" in r.text

    # Intentar upload_direct debe fallar
    files2 = {"file": ("photo2.jpg", b"fake-binary-2", "image/jpeg")}
    data2 = {"gender": "female", "legal_consent": "true"}
    r = await client.post(f"{settings.API_V1_STR}/profiles/upload-direct", headers=headers, files=files2, data=data2)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_leave_invalidation_and_status(client: AsyncClient):
    # Registro y login
    email = "leave@example.com"
    await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "pass123", "full_name": "Leaver"},
    )
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "pass123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # upload_direct para estar participando
    files = {"file": ("x.jpg", b"x", "image/jpeg")}
    data = {"gender": "female", "legal_consent": "true"}
    with patch("app.services.storage.storage_service.upload_file", return_value=True):
        r = await client.post(f"{settings.API_V1_STR}/profiles/upload-direct", headers=headers, files=files, data=data)
    assert r.status_code == 200
    created = r.json()
    pid = created["id"]

    # Confirmar estado participa
    r = await client.get(f"{settings.API_V1_STR}/profiles/me/participation-status", headers=headers)
    assert r.status_code == 200 and r.json()["participating"] is True

    # leave_game
    r = await client.post(f"{settings.API_V1_STR}/profiles/{pid}/leave", headers=headers)
    assert r.status_code == 200
    # Estado actualizado (no participar)
    r = await client.get(f"{settings.API_V1_STR}/profiles/me/participation-status", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["participating"] is False
    assert data["can_upload"] is True


@pytest.mark.asyncio
async def test_validation_requires_legal_consent(client: AsyncClient):
    email = "consent@example.com"
    await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "pass123", "full_name": "Consent"},
    )
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "pass123"},
    )
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # create_profile sin consentimiento
    r = await client.post(
        f"{settings.API_V1_STR}/profiles/",
        headers=headers,
        json={"gender": "female", "legal_consent": False},
    )
    assert r.status_code == 400
    assert "consentimiento legal" in r.text.lower()
