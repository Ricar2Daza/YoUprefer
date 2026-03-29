import pytest
from httpx import AsyncClient
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

@pytest.mark.asyncio
async def test_admin_approve_reject_and_reset_season(client: AsyncClient, db: AsyncSession):
    from app.core import security
    from app.models.user import User
    from app.models.profile import Profile, ProfileType, Gender
    from app.models.category import Category
    # Crear superusuario y categoría base
    super_email = "sysadmin@example.com"
    super_pass = "password123"
    super_user = User(email=super_email, hashed_password=security.get_password_hash(super_pass), full_name="Admin", is_active=True, is_superuser=True)
    db.add(super_user)
    await db.commit()
    await db.refresh(super_user)
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    # Login como superusuario
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": super_email, "password": super_pass})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Crear perfil pendiente
    pending_owner = User(email="pending_owner@example.com", hashed_password="x", full_name="Pending Owner", is_active=True)
    db.add(pending_owner)
    await db.commit()
    await db.refresh(pending_owner)
    pending = Profile(
        user_id=pending_owner.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/pending.jpg",
        is_active=True,
        is_approved=False,
        legal_consent=True
    )
    db.add(pending)
    await db.commit()
    await db.refresh(pending)
    # Aprobar perfil
    r = await client.post(f"{settings.API_V1_STR}/admin/{pending.id}/approve", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["is_approved"] is True
    # Rechazar otro perfil
    reject_owner = User(email="reject_owner@example.com", hashed_password="x", full_name="Reject Owner", is_active=True)
    db.add(reject_owner)
    await db.commit()
    await db.refresh(reject_owner)
    to_reject = Profile(
        user_id=reject_owner.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/reject.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True
    )
    db.add(to_reject)
    await db.commit()
    await db.refresh(to_reject)
    r = await client.post(f"{settings.API_V1_STR}/admin/{to_reject.id}/reject", headers=headers)
    assert r.status_code == 200, r.text
    # Reset de temporada
    # Crear perfiles aprobados con diferentes ELO
    profiles = []
    for i in range(6):
        u = User(email=f"season_user_{i}@example.com", hashed_password="x", full_name=f"S{i}", is_active=True)
        db.add(u)
        await db.commit()
        await db.refresh(u)
        p = Profile(
            user_id=u.id,
            category_id=category.id,
            type=ProfileType.REAL,
            gender=Gender.FEMALE,
            image_url=f"http://example.com/s{i}.jpg",
            is_active=True,
            is_approved=True,
            legal_consent=True
        )
        p.elo_score = 1200 + i * 50
        db.add(p)
        profiles.append(p)
    await db.commit()
    r = await client.post(f"{settings.API_V1_STR}/admin/season/reset", headers=headers)
    assert r.status_code == 200, r.text
    winners = r.json()
    assert isinstance(winners, list)
    for p in profiles:
        p.is_active = False
    await db.commit()

@pytest.mark.asyncio
async def test_categories_create_superuser_and_duplicate(client: AsyncClient, db: AsyncSession):
    # Login como superusuario existente
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "sysadmin@example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Crear categoría
    payload = {"name": "Moda", "slug": "moda", "description": "Moda y estilo", "is_active": True}
    r = await client.post(f"{settings.API_V1_STR}/categories/", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "moda"
    # Intentar duplicado
    r = await client.post(f"{settings.API_V1_STR}/categories/", json=payload, headers=headers)
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_badges_progress_and_award_flow(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.profile import Profile, ProfileType, Gender
    from app.models.category import Category
    # Registrar y loguear usuario común
    email = "badges@example.com"
    passwd = "password123"
    r = await client.post(f"{settings.API_V1_STR}/auth/register", json={"email": email, "password": passwd, "full_name": "Badge User"})
    assert r.status_code == 200
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": email, "password": passwd})
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Asegurar categoría
    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)
    # Crear perfil con alto ELO
    result_user = await db.execute(select(User).filter(User.email == email))
    user = result_user.scalars().first()
    p = Profile(
        user_id=user.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/top.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True
    )
    p.elo_score = 9999
    db.add(p)
    await db.commit()
    # Inicializar badges y consultar progreso
    r = await client.get(f"{settings.API_V1_STR}/badges/", headers=headers)
    assert r.status_code == 200
    r = await client.get(f"{settings.API_V1_STR}/badges/progress", headers=headers)
    assert r.status_code == 200
    # Chequear y otorgar badges
    r = await client.post(f"{settings.API_V1_STR}/badges/check", headers=headers)
    assert r.status_code == 200
    # Listar badges del usuario
    r = await client.get(f"{settings.API_V1_STR}/badges/me", headers=headers)
    assert r.status_code == 200
    awarded = r.json()
    assert isinstance(awarded, list)
    assert len(awarded) >= 1
    # Desactivar perfil para no afectar otras pruebas de temporada
    result_p = await db.execute(select(Profile).filter(Profile.user_id == user.id))
    for prof in result_p.scalars().all():
        prof.is_active = False
    await db.commit()

@pytest.mark.asyncio
async def test_notifications_list_patch_and_mark_all(client: AsyncClient, db: AsyncSession):
    from app.models.user import User
    from app.models.notification import Notification
    # Login como superusuario para usar su contexto
    r = await client.post(f"{settings.API_V1_STR}/auth/login/access-token", data={"username": "sysadmin@example.com", "password": "password123"})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    # Obtener superusuario
    result = await db.execute(select(User).filter(User.email == "sysadmin@example.com"))
    admin = result.scalars().first()
    # Crear notificaciones
    n1 = Notification(user_id=admin.id, type="info", payload={"msg": "hola"}, is_read=False)
    n2 = Notification(user_id=admin.id, type="alert", payload={"msg": "atencion"}, is_read=False)
    db.add(n1)
    db.add(n2)
    await db.commit()
    await db.refresh(n1)
    await db.refresh(n2)
    # Listar no leídas
    r = await client.get(f"{settings.API_V1_STR}/notifications?unread_only=true", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 2
    # Marcar una como leída
    r = await client.patch(f"{settings.API_V1_STR}/notifications/{n1.id}", json={"is_read": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["is_read"] is True
    # Marcar todas como leídas
    r = await client.post(f"{settings.API_V1_STR}/notifications/mark-all-read", headers=headers)
    assert r.status_code == 200
    # Verificar no leídas = 0
    r = await client.get(f"{settings.API_V1_STR}/notifications?unread_only=true", headers=headers)
    assert r.status_code == 200
    assert r.json()["total"] == 0

