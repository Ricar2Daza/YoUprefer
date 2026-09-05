import pytest
import json
from httpx import AsyncClient
from fastapi.testclient import TestClient
from app.core.config import settings
from app.core.security import create_access_token
from app.core.redis_client import redis_client
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.models.category import Category
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.main import app

# Integration Test
@pytest.mark.asyncio
async def test_full_integration_flow(client: AsyncClient, db: AsyncSession):
    # 1. Register User A (Voter)
    user_a_data = {
        "email": "voter@example.com",
        "password": "password123",
        "full_name": "Voter User"
    }
    r = await client.post(f"{settings.API_V1_STR}/auth/register", json=user_a_data)
    assert r.status_code == 200, f"Register failed: {r.text}"
    
    # 2. Login User A
    login_data = {
        "username": "voter@example.com",
        "password": "password123"
    }
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data=login_data)
    assert r.status_code == 200, f"Login failed: {r.text}"
    token_a = r.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}
    
    # 3. Create Category (needs to exist for profiles)
    # Check if exists or create one directly in DB
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    
    # 4. Create Candidates (User B & C) and their Profiles directly in DB
    # We bypass the API for profile creation to avoid S3/R2 dependency and ensure they are approved
    
    # User B
    user_b = User(email="candidate1@example.com", hashed_password="hashed_password", full_name="Candidate 1", is_active=True)
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
        is_approved=True, # Critical for voting
        legal_consent=True
    )
    db.add(profile_b)
    
    # User C
    user_c = User(email="candidate2@example.com", hashed_password="hashed_password", full_name="Candidate 2", is_active=True)
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
        is_approved=True, # Critical for voting
        legal_consent=True
    )
    db.add(profile_c)
    await db.commit()
    
    # 5. User A fetches pair
    # GET /profiles/pair?type=real&gender=female
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
    
    # Now vote should succeed even if User A has no own profile
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


def test_realtime_notifications_websocket_delivers_pubsub_event():
    """El WebSocket usa un ticket de corta duración (no el JWT) como credencial."""
    import secrets

    ticket = secrets.token_hex(16)
    redis_client.setex(f"ws_ticket:{ticket}", 30, "1")
    payload = {"type": "direct_message", "payload": {"from_user_id": 2}}
    message = json.dumps(payload)

    with TestClient(app) as c:
        with c.websocket_connect(
            f"{settings.API_V1_STR}/ws/notifications?ticket={ticket}"
        ) as ws:
            redis_client.publish("notifications:1", message)
            received = ws.receive_text()
            assert json.loads(received) == payload


def _assert_websocket_rejected(url: str):
    with TestClient(app) as c:
        try:
            with c.websocket_connect(url) as ws:
                ws.receive_text()
        except Exception:
            return
        raise AssertionError("WebSocket aceptó una conexión no autorizada")


def test_websocket_rejects_missing_ticket():
    """Conectar sin credencial debe ser rechazado."""
    _assert_websocket_rejected(f"{settings.API_V1_STR}/ws/notifications")


def test_websocket_rejects_invalid_ticket():
    """Un ticket inexistente debe ser rechazado."""
    _assert_websocket_rejected(
        f"{settings.API_V1_STR}/ws/notifications?ticket=not-a-real-ticket"
    )


def test_websocket_rejects_expired_ticket():
    """Un ticket vencido/consumido no debe volver a abrir la conexión."""
    import secrets

    ticket = secrets.token_hex(16)
    # Sin setex: el ticket nunca existió, por lo que debe ser rechazado
    _assert_websocket_rejected(
        f"{settings.API_V1_STR}/ws/notifications?ticket={ticket}"
    )
