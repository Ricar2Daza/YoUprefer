import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings


@pytest.mark.asyncio
async def test_auth_refresh_token_flow(client: AsyncClient, db: AsyncSession):
    """Test refresh token functionality"""
    from app.models.user import User
    from app.core import security
    
    # Create test user
    user = User(
        email="refreshuser@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Refresh User",
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Login to get tokens
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "refreshuser@example.com", "password": "password123"})
    assert r.status_code == 200
    tokens = r.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    
    refresh_token = tokens["refresh_token"]
    r = await client.post(f"{settings.API_V1_STR}/auth/refresh-token", json={"refresh_token": refresh_token})
    assert r.status_code == 200
    new_tokens = r.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens


@pytest.mark.asyncio
async def test_auth_refresh_token_invalid(client: AsyncClient):
    r = await client.post(f"{settings.API_V1_STR}/auth/refresh-token", json={"refresh_token": "invalid_token"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_auth_logout_flow(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.core import security
    
    # Create test user
    user = User(
        email="logoutuser@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Logout User",
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Login to get tokens
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "logoutuser@example.com", "password": "password123"})
    assert r.status_code == 200
    tokens = r.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    
    r = await client.post(
        f"{settings.API_V1_STR}/auth/logout",
        json={"refresh_token": refresh_token},
        headers=headers,
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_register_duplicate_email(client: AsyncClient, db: AsyncSession):
    """Test registration with duplicate email"""
    from app.models.user import User
    from app.core import security
    
    # Create existing user
    existing_user = User(
        email="duplicate@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Existing User",
        is_active=True
    )
    db.add(existing_user)
    await db.commit()
    
    # Try to register with same email
    r = await client.post(f"{settings.API_V1_STR}/auth/register", json={
        "email": "duplicate@example.com",
        "password": "password123",
        "full_name": "New User"
    })
    assert r.status_code == 400
    assert "El usuario con este correo ya existe en el sistema." in r.json()["detail"]


@pytest.mark.asyncio
async def test_auth_register_weak_password(client: AsyncClient):
    r = await client.post(f"{settings.API_V1_STR}/auth/register", json={
        "email": "weakpass@example.com",
        "password": "123",
        "full_name": "Weak Password User"
    })
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_auth_login_inactive_user(client: AsyncClient, db: AsyncSession):
    """Test login with inactive user"""
    from app.models.user import User
    from app.core import security
    
    # Create inactive user
    inactive_user = User(
        email="inactive@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Inactive User",
        is_active=False
    )
    db.add(inactive_user)
    await db.commit()
    
    # Try to login
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "inactive@example.com", "password": "password123"})
    assert r.status_code == 400
    assert "Usuario inactivo" in r.json()["detail"]


@pytest.mark.asyncio
async def test_auth_login_wrong_password(client: AsyncClient, db: AsyncSession):
    """Test login with wrong password"""
    from app.models.user import User
    from app.core import security
    
    # Create user
    user = User(
        email="wrongpass@example.com",
        hashed_password=security.get_password_hash("correctpassword"),
        full_name="Wrong Password User",
        is_active=True
    )
    db.add(user)
    await db.commit()
    
    # Try to login with wrong password
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "wrongpass@example.com", "password": "wrongpassword"})
    assert r.status_code == 400
    assert "Correo o contraseña incorrectos" in r.json()["detail"]


def _make_fake_httpx_client(*responses, return_for=None):
    """Build a fake httpx.AsyncClient factory.

    - If ``return_for`` is provided as a callable taking (url, **kwargs) and
      returning a response, that callable is used to choose the response per
      call (FIFO not used).
    - Otherwise the responses are returned in FIFO order.
    """
    if return_for is not None:
        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def get(self, url, *args, **kwargs):
                return return_for(url, **kwargs)

        return _FakeAsyncClient

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._call_index = 0
            self._responses = list(responses)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *args, **kwargs):
            resp = self._responses[min(self._call_index, len(self._responses) - 1)]
            self._call_index += 1
            return resp

    return _FakeAsyncClient


@pytest.mark.asyncio
async def test_oauth_google_unconfigured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", [])
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/google", json={"token": "irrelevant"})
    assert r.status_code == 503
    assert "no está configurado" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_google_rejects_wrong_aud(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", ["valid-client-id"])

    class _Resp:
        status_code = 200
        def json(self):
            return {
                "aud": "other-client-id",
                "iss": "accounts.google.com",
                "email": "user@example.com",
                "email_verified": "true",
            }

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_httpx_client(_Resp()))
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/google", json={"token": "any"})
    assert r.status_code == 401
    assert "otra aplicación" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_google_rejects_unverified_email(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", ["valid-client-id"])

    class _Resp:
        status_code = 200
        def json(self):
            return {
                "aud": "valid-client-id",
                "iss": "accounts.google.com",
                "email": "user@example.com",
                "email_verified": "false",
            }

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_httpx_client(_Resp()))
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/google", json={"token": "any"})
    assert r.status_code == 401
    assert "no está verificado" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_google_rejects_invalid_issuer(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", ["valid-client-id"])

    class _Resp:
        status_code = 200
        def json(self):
            return {
                "aud": "valid-client-id",
                "iss": "https://attacker.example.com",
                "email": "user@example.com",
                "email_verified": "true",
            }

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_httpx_client(_Resp()))
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/google", json={"token": "any"})
    assert r.status_code == 401
    assert "emisor" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_refresh_rotates_token(client: AsyncClient, db: AsyncSession):
    """El refresh debe devolver un nuevo refresh distinto al original (rotación)."""
    from app.models.user import User
    from app.core import security

    user = User(
        email="rotate@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Rotate User",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "rotate@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    initial_refresh = r.json()["refresh_token"]

    r = await client.post(
        f"{settings.API_V1_STR}/auth/refresh-token",
        json={"refresh_token": initial_refresh},
    )
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]

    assert new_refresh != initial_refresh


@pytest.mark.asyncio
async def test_auth_refresh_reuse_revokes_family(client: AsyncClient, db: AsyncSession):
    """Si un refresh ya consumido se vuelve a presentar, se revoca la familia."""
    from app.models.user import User
    from app.core import security

    user = User(
        email="reuse@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Reuse User",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "reuse@example.com", "password": "password123"},
    )
    assert r.status_code == 200
    refresh = r.json()["refresh_token"]

    # Primer refresh: OK
    r1 = await client.post(
        f"{settings.API_V1_STR}/auth/refresh-token",
        json={"refresh_token": refresh},
    )
    assert r1.status_code == 200

    # Segundo uso del MISMO refresh: debe detectar reuso
    r2 = await client.post(
        f"{settings.API_V1_STR}/auth/refresh-token",
        json={"refresh_token": refresh},
    )
    assert r2.status_code == 403
    assert "reutilizado" in r2.json()["detail"].lower() or "familia" in r2.json()["detail"].lower()

    # Incluso el nuevo refresh de la familia queda inutilizable
    new_refresh = r1.json()["refresh_token"]
    r3 = await client.post(
        f"{settings.API_V1_STR}/auth/refresh-token",
        json={"refresh_token": new_refresh},
    )
    assert r3.status_code == 403


@pytest.mark.asyncio
async def test_auth_refresh_rejects_token_without_jti(client: AsyncClient, db: AsyncSession):
    """Refresh tokens sin jti/fid deben ser rechazados (no rotación)."""
    from jose import jwt as _jwt
    from app.models.user import User
    from app.core import security

    user = User(
        email="legacy@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Legacy User",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    legacy_refresh = _jwt.encode(
        {"sub": str(user.id), "type": "refresh", "exp": __import__("datetime").datetime.utcnow() + __import__("datetime").timedelta(days=1)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    r = await client.post(
        f"{settings.API_V1_STR}/auth/refresh-token",
        json={"refresh_token": legacy_refresh},
    )
    assert r.status_code == 403
    assert "rotación" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_facebook_unconfigured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "FACEBOOK_OAUTH_APP_ID", None)
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/facebook", json={"token": "irrelevant"})
    assert r.status_code == 503
    assert "no está configurado" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_facebook_rejects_invalid_token(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "FACEBOOK_OAUTH_APP_ID", "123456")

    class _Resp:
        status_code = 400
        def json(self):
            return {"error": "invalid"}

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_httpx_client(_Resp()))
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/facebook", json={"token": "any"})
    assert r.status_code == 400
    assert "no se pudo validar" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oauth_facebook_rejects_mismatched_app_id(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "FACEBOOK_OAUTH_APP_ID", "123456")

    class _MeResp:
        status_code = 200
        def json(self):
            return {"id": "fb-user-id", "name": "FB User", "email": "fb@example.com"}

    class _DebugResp:
        status_code = 200
        def json(self):
            return {"data": {"is_valid": True, "app_id": "999999"}}

    def _router(url, **_kwargs):
        if "debug_token" in url:
            return _DebugResp()
        return _MeResp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _make_fake_httpx_client(return_for=_router))
    r = await client.post(f"{settings.API_V1_STR}/auth/oauth/facebook", json={"token": "any"})
    assert r.status_code == 401
    assert "otra aplicación" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_auth_me_endpoint(client: AsyncClient, db: AsyncSession):
    """Test getting current user info"""
    from app.models.user import User
    from app.core import security
    
    # Create test user
    user = User(
        email="meuser@example.com",
        hashed_password=security.get_password_hash("password123"),
        full_name="Me User",
        is_active=True
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Login
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "meuser@example.com", "password": "password123"})
    assert r.status_code == 200
    access_token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    
    # Get user info
    r = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    user_data = r.json()
    assert user_data["email"] == "meuser@example.com"
    assert user_data["full_name"] == "Me User"
    assert "id" in user_data
    assert "is_active" in user_data
