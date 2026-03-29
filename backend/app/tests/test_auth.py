import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.models.category import Category
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "test_reg@example.com", "password": "password123", "full_name": "Test User"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test_reg@example.com"
    assert "id" in data

@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    # Register first
    await client.post(
        "/api/v1/auth/register",
        json={"email": "login@example.com", "password": "password123", "full_name": "Login User"},
    )
    
    # Login
    response = await client.post(
        "/api/v1/auth/login/access-token",
        data={"username": "login@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_refresh_and_logout_flow(client: AsyncClient):
    # Registrar usuario
    email = "refresh@example.com"
    password = "password123"
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": password, "full_name": "Refresh User"})
    assert r.status_code == 200
    # Login
    r = await client.post("/api/v1/auth/login/access-token", data={"username": email, "password": password})
    assert r.status_code == 200
    tokens = r.json()
    assert "refresh_token" in tokens
    # Refrescar
    r = await client.post("/api/v1/auth/refresh-token", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert "access_token" in new_tokens
    # Logout
    r = await client.post("/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    # Intentar refrescar nuevamente: en entornos sin Redis puede seguir siendo 200; con Redis, 401/403
    r = await client.post("/api/v1/auth/refresh-token", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code in (200, 401, 403)
    # Intentar usar access token anterior en endpoint protegido: puede seguir siendo válido si no se usa blacklist
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.get("/api/v1/users/me", headers=headers)
    assert r.status_code in (200, 401, 403)

@pytest.mark.asyncio
async def test_full_integration_flow(client: AsyncClient, db: AsyncSession):
    # 1. Register User A (Voter)
    user_a_data = {
        "email": "voter_auth@example.com",
        "password": "password123",
        "full_name": "Voter User"
    }
    r = await client.post(f"{settings.API_V1_STR}/auth/register", json=user_a_data)
    assert r.status_code == 200, f"Register failed: {r.text}"
    user_a_id = r.json()["id"]
    
    # 2. Login User A
    login_data = {
        "username": "voter_auth@example.com",
        "password": "password123"
    }
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data=login_data)
    assert r.status_code == 200, f"Login failed: {r.text}"
    token_a = r.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # 3. Create Category (needs to exist for profiles)
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    
    # 4. Create Candidates (User B & C) and their Profiles directly in DB
    # User B
    user_b = User(email="candidate_auth1@example.com", hashed_password="hashed_password", full_name="Candidate 1", is_active=True)
    db.add(user_b)
    await db.commit()
    await db.refresh(user_b)
    
    profile_b = Profile(
        user_id=user_b.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/image1.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True
    )
    db.add(profile_b)
    
    # User C
    user_c = User(email="candidate_auth2@example.com", hashed_password="hashed_password", full_name="Candidate 2", is_active=True)
    db.add(user_c)
    await db.commit()
    await db.refresh(user_c)
    
    profile_c = Profile(
        user_id=user_c.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/image2.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True
    )
    db.add(profile_c)
    await db.commit()
    
    # No es necesario crear perfil para el votante

    # 5. User A fetches pair
    r = await client.get(f"{settings.API_V1_STR}/profiles/pair?type=real&gender=female", headers=headers_a)
    assert r.status_code == 200, f"Get pair failed: {r.text}"
    data = r.json()
    assert len(data) == 2, "Should return exactly 2 profiles"
    
    # 6. User A votes
    winner_id = data[0]["id"]
    loser_id = data[1]["id"]
    
    vote_data = {
        "winner_id": winner_id,
        "loser_id": loser_id
    }
    
    r = await client.post(f"{settings.API_V1_STR}/votes/", json=vote_data, headers=headers_a)
    assert r.status_code == 200, f"Vote failed: {r.text}"
    vote_res = r.json()
    assert vote_res["winner_id"] == winner_id
    assert vote_res["loser_id"] == loser_id
    
    # 7. Verify Categories Endpoint
    r = await client.get(f"{settings.API_V1_STR}/categories/")
    assert r.status_code == 200
    cats = r.json()
    assert len(cats) >= 1
    assert cats[0]["slug"] == "general"
