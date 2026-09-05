import uuid
import itertools
import pytest
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core import security
from app.core.config import settings
from app.models.user import User
from app.models.category import Category
from app.models.custom_vote import (
    CustomVote,
    CustomVoteParticipant,
    CustomVotePhoto,
    CustomVoteBallot,
)

_seq = itertools.count(1)
AUTH_STR = settings.API_V1_STR


async def _register_login(client: AsyncClient, tag: str, password: str = "password123"):
    email = f"{tag}_{next(_seq)}@{uuid.uuid4().hex[:8]}.com"
    r = await client.post(
        f"{AUTH_STR}/auth/register",
        json={"email": email, "password": password, "full_name": tag},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{AUTH_STR}/auth/login/access-token",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _ensure_category(db: AsyncSession) -> Category:
    slug = f"cv-cat-{uuid.uuid4().hex[:8]}"
    cat = Category(name=f"Cat {slug}", slug=slug, is_active=True)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


def _image_files(n=1, name: str = "a.jpg"):
    return [("files", (name, b"\xff\xd8\xff\xe0" + b"\x00" * 64, "image/jpeg")) for _ in range(n)]


async def _create_public_vote(client: AsyncClient, db: AsyncSession, headers, title="Reto"):
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": title, "category_id": cat.id, "description": ""},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    vote = r.json()
    return vote, cat


# ---------------------------------------------------------------------------
# CREAR VOTACIÓN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_custom_vote_happy_path(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvc")
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Mi reto", "category_id": cat.id, "description": "desc"},
        files=_image_files(2, "pic.jpg"),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    vote = r.json()
    assert vote["title"] == "Mi reto"
    assert vote["description"] == "desc"
    assert vote["category_id"] == cat.id
    assert vote["is_active"] is True
    assert len(vote["participants"]) == 1
    owner = vote["participants"][0]
    assert owner["role"] == "owner"
    assert len(owner["photos"]) == 2
    assert owner["photos"][0]["image_url"] != ""


@pytest.mark.asyncio
async def test_create_custom_vote_requires_title(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvtitle")
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "   ", "category_id": cat.id},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_title_too_long(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvlong")
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "x" * 121, "category_id": cat.id},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_requires_files(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvnofile")
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Sin foto", "category_id": cat.id},
        files=[],
        headers=headers,
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_non_image_rejected(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvnona")
    cat = await _ensure_category(db)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "No imagen", "category_id": cat.id},
        files=[("files", ("x.txt", b"hola", "text/plain"))],
        headers=headers,
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_category_not_found(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvbadcat")
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Cat", "category_id": 999999},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_self_challenge_rejected(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvself")
    # need user id of current user -> create a vote without challenge then inspect
    cat = await _ensure_category(db)
    r1 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "A", "category_id": cat.id},
        files=_image_files(1),
        headers=headers,
    )
    own_id = r1.json()["owner_id"]
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "B", "category_id": cat.id, "challenged_user_id": own_id},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_create_custom_vote_challenge_other_user(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvchall")
    challenger = await _register_login(client, "cvchal2")
    # challenger user id: create a throwaway vote
    cat = await _ensure_category(db)
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=challenger,
    )
    challenged_uid = r0.json()["owner_id"]

    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Reto", "category_id": cat.id, "challenged_user_id": challenged_uid},
        files=_image_files(1),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    vote = r.json()
    roles = {p["role"] for p in vote["participants"]}
    assert roles == {"challenger", "challenged"}


# ---------------------------------------------------------------------------
# LISTAR / OBTENER
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_custom_votes_and_filters(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvlist")
    cat = await _ensure_category(db)
    for i in range(3):
        await _create_public_vote(client, db, headers, title=f"v{i}")

    r = await client.get(f"{AUTH_STR}/custom-votes/", headers=headers)
    assert r.status_code == 200
    titles = [v["title"] for v in r.json()]
    assert "v0" in titles and "v2" in titles

    r = await client.get(f"{AUTH_STR}/custom-votes/?category_id={cat.id}", headers=headers)
    assert r.status_code == 200
    assert all(v["category_id"] == cat.id for v in r.json())


@pytest.mark.asyncio
async def test_get_custom_vote_not_found(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvget404")
    r = await client.get(f"{AUTH_STR}/custom-votes/999999", headers=headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_custom_vote_detail(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvget")
    vote, _ = await _create_public_vote(client, db, headers)
    r = await client.get(f"{AUTH_STR}/custom-votes/{vote['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == vote["id"]
    assert len(r.json()["participants"]) == 1


# ---------------------------------------------------------------------------
# UNIRSE A RETO
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_join_challenge_requires_challenged_role(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvo")
    stranger = await _register_login(client, "cvstr")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    r = await client.post(
        f"{AUTH_STR}/custom-votes/{vote['id']}/join",
        files=_image_files(1),
        headers=stranger,
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_join_challenge_happy_path(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvj1")
    challenged = await _register_login(client, "cvj2")
    cat = await _ensure_category(db)
    # challenger creates vote with challenged user
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=challenged,
    )
    challenged_uid = r0.json()["owner_id"]
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Reto", "category_id": cat.id, "challenged_user_id": challenged_uid},
        files=_image_files(1),
        headers=headers,
    )
    vote = r.json()
    vid = vote["id"]

    r = await client.post(
        f"{AUTH_STR}/custom-votes/{vid}/join",
        files=_image_files(1, "challenged.jpg"),
        headers=challenged,
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    by_role = {p["role"]: p for p in updated["participants"]}
    assert len(by_role["challenged"]["photos"]) == 1


@pytest.mark.asyncio
async def test_join_challenge_already_has_photos(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvj3")
    challenged = await _register_login(client, "cvj4")
    cat = await _ensure_category(db)
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=challenged,
    )
    challenged_uid = r0.json()["owner_id"]
    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Reto", "category_id": cat.id, "challenged_user_id": challenged_uid},
        files=_image_files(1),
        headers=headers,
    )
    vid = r.json()["id"]
    await client.post(f"{AUTH_STR}/custom-votes/{vid}/join", files=_image_files(1), headers=challenged)
    r2 = await client.post(f"{AUTH_STR}/custom-votes/{vid}/join", files=_image_files(1), headers=challenged)
    assert r2.status_code == 400, r2.text


# ---------------------------------------------------------------------------
# VOTAR
# ---------------------------------------------------------------------------

async def _vote_on(client, headers, vid, photo_id):
    return await client.post(
        f"{AUTH_STR}/custom-votes/{vid}/vote",
        json={"photo_id": photo_id},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_vote_custom_vote_happy_path(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvvo")
    voter = await _register_login(client, "cvvoter")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    photo_id = vote["participants"][0]["photos"][0]["id"]

    r = await _vote_on(client, voter, vote["id"], photo_id)
    assert r.status_code == 200, r.text

    stored = (await db.execute(select(CustomVoteBallot).filter(CustomVoteBallot.vote_id == vote["id"]))).scalars().first()
    assert stored is not None
    assert stored.photo_id == photo_id


@pytest.mark.asyncio
async def test_vote_duplicate_rejected(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvvdup")
    voter = await _register_login(client, "cvvdup2")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    photo_id = vote["participants"][0]["photos"][0]["id"]

    r1 = await _vote_on(client, voter, vote["id"], photo_id)
    assert r1.status_code == 200, r1.text
    r2 = await _vote_on(client, voter, vote["id"], photo_id)
    assert r2.status_code == 400, r2.text


@pytest.mark.asyncio
async def test_vote_photo_not_found(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvvpnf")
    voter = await _register_login(client, "cvvpnf2")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    r = await _vote_on(client, voter, vote["id"], 999999)
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_vote_expired_rejected(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvvexp")
    voter = await _register_login(client, "cvvexp2")
    cat = await _ensure_category(db)
    # create an already-expired vote directly in DB
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=owner_hdr,
    )
    owner_id = r0.json()["owner_id"]
    vote = CustomVote(
        owner_id=owner_id,
        category_id=cat.id,
        title="Expirado",
        is_active=True,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        expiring_notified=False,
    )
    db.add(vote)
    await db.flush()
    part = CustomVoteParticipant(vote_id=vote.id, user_id=owner_id, role="owner")
    db.add(part)
    await db.flush()
    db.add(CustomVotePhoto(participant_id=part.id, image_url="http://example.com/x.jpg", object_name=None))
    await db.commit()
    await db.refresh(vote)

    r = await _vote_on(client, voter, vote.id, 1)
    assert r.status_code in (400, 404), r.text


# ---------------------------------------------------------------------------
# RESULTADOS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_vote_results_counts(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvres")
    v1 = await _register_login(client, "cvresv1")
    v2 = await _register_login(client, "cvresv2")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    photo_id = vote["participants"][0]["photos"][0]["id"]

    await _vote_on(client, v1, vote["id"], photo_id)
    await _vote_on(client, v2, vote["id"], photo_id)

    r = await client.get(f"{AUTH_STR}/custom-votes/{vote['id']}/results", headers=owner_hdr)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["custom_vote_id"] == vote["id"]
    assert data["photo_counts"][str(photo_id)] == 2
    owner_uid = vote["participants"][0]["user_id"]
    assert data["user_counts"][str(owner_uid)] == 2


@pytest.mark.asyncio
async def test_custom_vote_results_zero_counts(client: AsyncClient, db: AsyncSession):
    owner_hdr = await _register_login(client, "cvres0")
    vote, _ = await _create_public_vote(client, db, owner_hdr)
    r = await client.get(f"{AUTH_STR}/custom-votes/{vote['id']}/results", headers=owner_hdr)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["custom_vote_id"] == vote["id"]
    owner_uid = vote["participants"][0]["user_id"]
    assert data["user_counts"][str(owner_uid)] == 0
    assert data["photo_counts"] == {}


@pytest.mark.asyncio
async def test_custom_vote_results_not_found(client: AsyncClient, db: AsyncSession):
    headers = await _register_login(client, "cvres404")
    r = await client.get(f"{AUTH_STR}/custom-votes/999999/results", headers=headers)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# BLOQUEOS
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blocked_participant_hidden_from_list(client: AsyncClient, db: AsyncSession):
    creator = await _register_login(client, "cvbcr")
    blocker = await _register_login(client, "cvbbl")
    victim = await _register_login(client, "cvbvic")
    cat = await _ensure_category(db)
    # victim creates a vote
    target_id = None
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=victim,
    )
    target_id = r0.json()["owner_id"]
    # creator also makes a vote
    await _create_public_vote(client, db, creator, "mio")
    # blocker blocks target
    r = await client.post(f"{AUTH_STR}/users/{target_id}/block", headers=blocker)
    assert r.status_code in (200, 201), r.text

    list_r = await client.get(f"{AUTH_STR}/custom-votes/", headers=blocker)
    assert list_r.status_code == 200
    for v in list_r.json():
        for p in v["participants"]:
            assert p["user_id"] != target_id, "votación con participante bloqueado no oculta"


@pytest.mark.asyncio
async def test_send_challenge_to_blocked_user_forbidden(client: AsyncClient, db: AsyncSession):
    challenger = await _register_login(client, "cvbc2")
    victim = await _register_login(client, "cvbc2v")
    cat = await _ensure_category(db)
    r0 = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "tmp", "category_id": cat.id},
        files=_image_files(1),
        headers=victim,
    )
    victim_uid = r0.json()["owner_id"]
    # challenger blocks victim
    r = await client.post(f"{AUTH_STR}/users/{victim_uid}/block", headers=challenger)
    assert r.status_code in (200, 201), r.text

    r = await client.post(
        f"{AUTH_STR}/custom-votes/",
        data={"title": "Reto", "category_id": cat.id, "challenged_user_id": victim_uid},
        files=_image_files(1),
        headers=challenger,
    )
    assert r.status_code == 403, r.text
