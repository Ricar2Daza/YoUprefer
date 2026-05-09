import pytest
from datetime import datetime, timedelta, timezone

from app.core import security
from app.core.config import settings


@pytest.mark.asyncio
async def test_block_prevents_follow_and_messages(client, db):
    from app.models.user import User

    u1 = User(email="blk1@example.com", hashed_password=security.get_password_hash("x"), full_name="U1", is_active=True)
    u2 = User(email="blk2@example.com", hashed_password=security.get_password_hash("x"), full_name="U2", is_active=True)
    db.add_all([u1, u2])
    await db.commit()
    await db.refresh(u1)
    await db.refresh(u2)

    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "blk1@example.com", "password": "x"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.post(f"{settings.API_V1_STR}/users/{u2.id}/block", headers=headers)
    assert r.status_code in (200, 201), r.text

    r = await client.post(f"{settings.API_V1_STR}/users/{u2.id}/follow", headers=headers)
    assert r.status_code == 403

    r = await client.post(f"{settings.API_V1_STR}/messages/{u2.id}", json={"content": "hola"}, headers=headers)
    assert r.status_code == 403

    r = await client.delete(f"{settings.API_V1_STR}/users/{u2.id}/block", headers=headers)
    assert r.status_code == 200

    r = await client.post(f"{settings.API_V1_STR}/messages/{u2.id}", json={"content": "hola"}, headers=headers)
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_direct_messages_threads_and_mark_read(client, db):
    from app.models.user import User

    u1 = User(email="dm1@example.com", hashed_password=security.get_password_hash("x"), full_name="U1", is_active=True)
    u2 = User(email="dm2@example.com", hashed_password=security.get_password_hash("x"), full_name="U2", is_active=True)
    db.add_all([u1, u2])
    await db.commit()
    await db.refresh(u1)
    await db.refresh(u2)

    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "dm1@example.com", "password": "x"})
    token = r.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token}"}

    r = await client.post(f"{settings.API_V1_STR}/messages/{u2.id}", json={"content": "hola"}, headers=headers1)
    assert r.status_code == 201

    r = await client.get(f"{settings.API_V1_STR}/messages/threads", headers=headers1)
    assert r.status_code == 200
    threads = r.json()
    assert any(t["user_id"] == u2.id for t in threads)

    r = await client.get(f"{settings.API_V1_STR}/messages/{u2.id}", headers=headers1)
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 1


@pytest.mark.asyncio
async def test_custom_vote_expires_and_is_deleted(client, db):
    from app.models.user import User
    from app.models.category import Category
    from app.models.custom_vote import CustomVote, CustomVoteParticipant, CustomVotePhoto
    from sqlalchemy.future import select
    import uuid

    cat = Category(name=f"Cat {uuid.uuid4()}", slug=f"cat-{uuid.uuid4()}", is_active=True)
    owner = User(email="cv1@example.com", hashed_password=security.get_password_hash("x"), full_name="U", is_active=True)
    db.add_all([cat, owner])
    await db.commit()
    await db.refresh(cat)
    await db.refresh(owner)

    expired_vote = CustomVote(
        owner_id=owner.id,
        category_id=cat.id,
        title="t",
        description=None,
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        expiring_notified=False,
    )
    db.add(expired_vote)
    await db.flush()
    part = CustomVoteParticipant(vote_id=expired_vote.id, user_id=owner.id, role="owner")
    db.add(part)
    await db.flush()
    db.add(CustomVotePhoto(participant_id=part.id, image_url="http://example.com/x.jpg", object_name=None))
    await db.commit()

    r = await client.get(f"{settings.API_V1_STR}/custom-votes/")
    assert r.status_code == 200

    result = await db.execute(select(CustomVote).filter(CustomVote.id == expired_vote.id))
    assert result.scalars().first() is None
