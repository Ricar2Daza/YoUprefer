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
