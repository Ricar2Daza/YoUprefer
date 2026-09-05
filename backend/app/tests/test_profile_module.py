import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.models.profile import Profile, ProfileType, Gender
from app.models.category import Category
from app.models.user import User


@pytest.mark.asyncio
async def test_profile_loads_user_and_own_profiles(client: AsyncClient, db: AsyncSession):
    email = "profload@example.com"
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "password123", "full_name": "Profile Loader"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # /users/me carga los datos del usuario
    me = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert me.status_code == 200, me.text
    user = me.json()
    assert user["email"] == email
    assert user["full_name"] == "Profile Loader"

    # /profiles/me devuelve los perfiles propios (inicialmente vacío)
    profs = await client.get(f"{settings.API_V1_STR}/profiles/me", headers=headers)
    assert profs.status_code == 200, profs.text
    assert profs.json() == []

    # Estado de participación sin foto
    status = await client.get(f"{settings.API_V1_STR}/profiles/me/participation-status", headers=headers)
    assert status.status_code == 200, status.text
    assert status.json()["participating"] is False


@pytest.mark.asyncio
async def test_profile_update_persists_to_db(client: AsyncClient, db: AsyncSession):
    email = "profileput@example.com"
    r = await client.post(
        f"{settings.API_V1_STR}/auth/register",
        json={"email": email, "password": "password123", "full_name": "Old Name"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": email, "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    updated = await client.put(
        f"{settings.API_V1_STR}/users/me",
        json={"full_name": "Nuevo Nombre", "bio": "Una bio de prueba"},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["full_name"] == "Nuevo Nombre"
    assert body["bio"] == "Una bio de prueba"

    # Verificar que el cambio quedó persistido en la BD y en /users/me nuevamente.
    row = (await db.execute(select(User).filter(User.email == email))).scalars().first()
    assert row is not None
    assert row.full_name == "Nuevo Nombre"
    assert row.bio == "Una bio de prueba"

    me2 = await client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert me2.json()["full_name"] == "Nuevo Nombre"


@pytest.mark.asyncio
async def test_profile_update_rejects_duplicate_email(client: AsyncClient, db: AsyncSession):
    # Dos usuarios
    for i, mail in enumerate(["first@example.com", "second@example.com"]):
        r = await client.post(
            f"{settings.API_V1_STR}/auth/register",
            json={"email": mail, "password": "password123", "full_name": f"User {i}"},
        )
        assert r.status_code == 200, r.text
    r = await client.post(
        f"{settings.API_V1_STR}/auth/login/access-token",
        data={"username": "first@example.com", "password": "password123"},
    )
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Intentar tomar el email del segundo usuario -> 400
    r2 = await client.put(
        f"{settings.API_V1_STR}/users/me",
        json={"email": "second@example.com"},
        headers=headers,
    )
    assert r2.status_code == 400, r2.text


@pytest.mark.asyncio
async def test_get_ranking_public_and_profile_shape(client: AsyncClient, db: AsyncSession):
    # Crear un perfil aprobado directamente.
    cat_result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = cat_result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    user = User(email="rank_cand_public@example.com", hashed_password="x", full_name="Cand", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    profile = Profile(
        user_id=user.id, category_id=category.id, type=ProfileType.REAL, gender=Gender.FEMALE,
        image_url="http://example.com/rank.jpg", is_active=True, is_approved=True, legal_consent=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    # Ranking público (sin token).
    r = await client.get(f"{settings.API_V1_STR}/profiles/ranking?type=real&limit=10")
    assert r.status_code == 200, r.text
    items = r.json()
    assert any(p["id"] == profile.id for p in items)
    target = next(p for p in items if p["id"] == profile.id)
    # Forma de datos esperada por el frontend.
    for field in ("id", "image_url", "elo_score", "win_count", "voted_count", "user_id"):
        assert field in target, f"Falta campo {field} en respuesta de ranking"
