import pytest
import itertools
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.profile import Profile, ProfileType, Gender
from app.models.user import User
from app.models.category import Category
from app.models.vote import Vote

_profile_seq = itertools.count(1)


async def _ensure_category(db: AsyncSession) -> Category:
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    return category


async def _register_and_login(client: AsyncClient, tag: str, password: str = "password123"):
    email = f"{tag}_{next(_profile_seq)}@example.com"
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": password, "full_name": tag},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _create_approved_profile(db: AsyncSession, category: Category, elo: int = 1500) -> Profile:
    n = next(_profile_seq)
    user = User(email=f"cand_{elo}_{n}@example.com", hashed_password="x", full_name="Cand", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    profile = Profile(
        user_id=user.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url=f"http://example.com/{elo}.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True,
        elo_score=elo,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# MÓDULO DE VOTACIÓN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vote_registers_and_updates_elo_and_counts(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "voteok")
    category = await _ensure_category(db)
    winner = await _create_approved_profile(db, category, elo=1500)
    loser = await _create_approved_profile(db, category, elo=1200)

    r = await client.post(
        f"{settings.API_V1_STR}/votes/",
        json={"winner_id": winner.id, "loser_id": loser.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    vote = r.json()
    assert vote["winner_id"] == winner.id
    assert vote["loser_id"] == loser.id

    # El ganador debe ganar puntuación ELO, el perdedor perder.
    rep_winner = (await db.execute(select(Profile).filter(Profile.id == winner.id))).scalars().first()
    rep_loser = (await db.execute(select(Profile).filter(Profile.id == loser.id))).scalars().first()
    assert rep_winner.elo_score > 1500
    assert rep_loser.elo_score < 1200
    # Recuentos: ganador +1 victoria y +1 duelo; perdedor +1 duelo.
    assert rep_winner.win_count == 1
    assert rep_winner.voted_count == 1
    assert rep_loser.win_count == 0
    assert rep_loser.voted_count == 1

    # El voto queda persistido en BD.
    stored = (await db.execute(
        select(Vote).filter(Vote.winner_id == winner.id, Vote.loser_id == loser.id)
    )).scalars().first()
    assert stored is not None


@pytest.mark.asyncio
async def test_duplicate_vote_same_direction_rejected(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "dup1")
    category = await _ensure_category(db)
    winner = await _create_approved_profile(db, category)
    loser = await _create_approved_profile(db, category)

    payload = {"winner_id": winner.id, "loser_id": loser.id}
    r1 = await client.post(f"{settings.API_V1_STR}/votes/", json=payload, headers=headers)
    assert r1.status_code == 200, r1.text
    # Segunda vez, misma dirección -> 409
    r2 = await client.post(f"{settings.API_V1_STR}/votes/", json=payload, headers=headers)
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"


@pytest.mark.asyncio
async def test_duplicate_vote_reversed_direction_rejected(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "dup2")
    category = await _ensure_category(db)
    a = await _create_approved_profile(db, category)
    b = await _create_approved_profile(db, category)

    r1 = await client.post(f"{settings.API_V1_STR}/votes/", json={"winner_id": a.id, "loser_id": b.id}, headers=headers)
    assert r1.status_code == 200, r1.text
    # Revertido (b gana a a): mismo emparejamiento, debe rechazarse.
    r2 = await client.post(f"{settings.API_V1_STR}/votes/", json={"winner_id": b.id, "loser_id": a.id}, headers=headers)
    assert r2.status_code == 409, f"Expected 409, got {r2.status_code}: {r2.text}"


@pytest.mark.asyncio
async def test_vote_same_profile_rejected(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "selfvote")
    category = await _ensure_category(db)
    p = await _create_approved_profile(db, category)
    r = await client.post(
        f"{settings.API_V1_STR}/votes/",
        json={"winner_id": p.id, "loser_id": p.id},
        headers=headers,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_vote_requires_approved_active_profiles(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "inactivevote")
    category = await _ensure_category(db)
    ok = await _create_approved_profile(db, category)
    user = User(email="inact_cand@example.com", hashed_password="x", full_name="Cand", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    bad = Profile(
        user_id=user.id, category_id=category.id, type=ProfileType.REAL, gender=Gender.FEMALE,
        image_url="http://example.com/x.jpg", is_active=False, is_approved=False, legal_consent=True,
    )
    db.add(bad)
    await db.commit()
    await db.refresh(bad)

    r = await client.post(
        f"{settings.API_V1_STR}/votes/",
        json={"winner_id": ok.id, "loser_id": bad.id},
        headers=headers,
    )
    assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# MÓDULO DE RANKING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ranking_orders_by_elo_desc(client: AsyncClient, db: AsyncSession):
    category = await _ensure_category(db)
    # Perfiles con ELO distintos conocidos.
    await _create_approved_profile(db, category, elo=1000)
    await _create_approved_profile(db, category, elo=1300)
    await _create_approved_profile(db, category, elo=1100)

    r = await client.get(f"{settings.API_V1_STR}/profiles/ranking?type=real&limit=10")
    assert r.status_code == 200, r.text
    items = r.json()
    # Solo deberían devolverse los aprobados/activos (los recién creados).
    selected = [p for p in items if p["elo_score"] in (1000, 1100, 1300)]
    scores = [p["elo_score"] for p in selected]
    assert scores == sorted(scores, reverse=True), f"Ranking no ordenado por ELO: {scores}"


@pytest.mark.asyncio
async def test_ranking_reflects_score_update_after_vote(client: AsyncClient, db: AsyncSession):
    headers = await _register_and_login(client, "rankup")
    category = await _ensure_category(db)
    winner = await _create_approved_profile(db, category, elo=1500)
    loser = await _create_approved_profile(db, category, elo=1200)

    before_w = (await db.execute(select(Profile).filter(Profile.id == winner.id))).scalars().first().elo_score

    r = await client.post(
        f"{settings.API_V1_STR}/votes/",
        json={"winner_id": winner.id, "loser_id": loser.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rank = await client.get(f"{settings.API_V1_STR}/profiles/ranking?type=real&limit=50")
    assert rank.status_code == 200, rank.text
    by_id = {p["id"]: p for p in rank.json()}
    assert winner.id in by_id
    assert by_id[winner.id]["elo_score"] > before_w
    assert by_id[winner.id]["win_count"] == 1
