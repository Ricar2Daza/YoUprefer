import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core import security


@pytest.mark.asyncio
async def test_notifications_list_pagination(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.notification import Notification

    user = User(
        email="notifuser@example.com",
        hashed_password=security.get_password_hash("x"),
        full_name="Notif User",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    for i in range(5):
        notification = Notification(
            user_id=user.id,
            type="info",
            payload={"msg": f"Test notification {i}"},
            is_read=False
        )
        db.add(notification)
    await db.commit()
    
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={
        "username": "notifuser@example.com",
        "password": "x"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test pagination
    r = await client.get(f"{settings.API_V1_STR}/notifications?limit=2&offset=1", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 1
    assert data["total"] >= 5


@pytest.mark.asyncio
async def test_notifications_unread_filter(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.notification import Notification

    user = User(
        email="notifunread@example.com",
        hashed_password=security.get_password_hash("x"),
        full_name="Notif Unread",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    for i in range(3):
        notification = Notification(
            user_id=user.id,
            type="info",
            payload={"msg": f"Test notification {i}"},
            is_read=(i == 0)  # First one is read
        )
        db.add(notification)
    await db.commit()
    
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={
        "username": "notifunread@example.com",
        "password": "x"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test unread filter
    r = await client.get(f"{settings.API_V1_STR}/notifications?unread_only=true", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 2  # Should only get unread notifications
    assert all(not item["is_read"] for item in data["items"])


@pytest.mark.asyncio
async def test_notifications_forbidden_access(client: AsyncClient):
    r = await client.get(f"{settings.API_V1_STR}/notifications")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_notifications_mark_read(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.notification import Notification

    user = User(
        email="notifread@example.com",
        hashed_password=security.get_password_hash("x"),
        full_name="Notif Read",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    notification = Notification(
        user_id=user.id,
        type="info",
        payload={"msg": "Test notification"},
        is_read=False
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)
    
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={
        "username": "notifread@example.com",
        "password": "x"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Mark as read
    r = await client.patch(f"{settings.API_V1_STR}/notifications/{notification.id}", json={"is_read": True}, headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["is_read"] == True


@pytest.mark.asyncio
async def test_notifications_mark_read_not_found(client: AsyncClient, db: AsyncSession):
    from app.models.user import User

    user = User(
        email="notifnotfound@example.com",
        hashed_password=security.get_password_hash("x"),
        full_name="Notif Not Found",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={
        "username": "notifnotfound@example.com",
        "password": "x"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Try to mark non-existent notification
    r = await client.patch(f"{settings.API_V1_STR}/notifications/99999", json={"is_read": True}, headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_notifications_mark_all_read(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.notification import Notification

    user = User(
        email="notifallread@example.com",
        hashed_password=security.get_password_hash("x"),
        full_name="Notif All Read",
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    for i in range(3):
        notification = Notification(
            user_id=user.id,
            type="info",
            payload={"msg": f"Test notification {i}"},
            is_read=False
        )
        db.add(notification)
    await db.commit()
    
    # Login to get token
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={
        "username": "notifallread@example.com",
        "password": "x"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    # Mark all as read
    r = await client.post(f"{settings.API_V1_STR}/notifications/mark-all-read", headers=headers)
    assert r.status_code == 200
    
    # Verify all are read
    r = await client.get(f"{settings.API_V1_STR}/notifications?unread_only=true", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 0
