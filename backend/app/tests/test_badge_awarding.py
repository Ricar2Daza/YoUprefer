import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app.services.badge_service import badge_service
from app.models.badge import Badge, UserBadge
from app.models.notification import Notification
from app.models.user import User
from app.models.profile import Profile, ProfileType, Gender
from app.models.category import Category


@pytest.mark.asyncio
async def test_check_and_award_badges_is_idempotent(db: AsyncSession):
    # Usuario con un perfil en el top 1 del ranking global.
    user = User(email="badge_idem@example.com", hashed_password="x", full_name="Idem", is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    result = await db.execute(select(Category).filter(Category.slug == "general"))
    category = result.scalars().first()
    if not category:
        category = Category(name="General", slug="general", is_active=True)
        db.add(category)
        await db.commit()
        await db.refresh(category)

    profile = Profile(
        user_id=user.id,
        category_id=category.id,
        type=ProfileType.REAL,
        gender=Gender.FEMALE,
        image_url="http://example.com/top_idem.jpg",
        is_active=True,
        is_approved=True,
        legal_consent=True,
    )
    profile.elo_score = 99999
    db.add(profile)
    await db.commit()

    # Asegura badges por defecto presentes.
    await badge_service.init_default_badges(db)

    # Primera pasada: debe otorgar la(s) badge(s) de ranking que corresponda.
    await badge_service.check_and_award_badges(db, user.id)

    badge_count_1 = (
        await db.execute(
            select(func.count()).select_from(UserBadge).filter(UserBadge.user_id == user.id)
        )
    ).scalar_one()
    notif_count_1 = (
        await db.execute(
            select(func.count()).select_from(Notification).filter(Notification.user_id == user.id)
        )
    ).scalar_one()

    assert badge_count_1 >= 1

    # Segunda pasada: no debe duplicar badges ni notificaciones.
    await badge_service.check_and_award_badges(db, user.id)

    badge_count_2 = (
        await db.execute(
            select(func.count()).select_from(UserBadge).filter(UserBadge.user_id == user.id)
        )
    ).scalar_one()
    notif_count_2 = (
        await db.execute(
            select(func.count()).select_from(Notification).filter(Notification.user_id == user.id)
        )
    ).scalar_one()

    assert badge_count_2 == badge_count_1
    assert notif_count_2 == notif_count_1

    # No debe haber UserBadge duplicada para la misma badge del mismo usuario.
    dup = await db.execute(
        select(UserBadge.user_id, UserBadge.badge_id)
        .filter(UserBadge.user_id == user.id)
        .group_by(UserBadge.user_id, UserBadge.badge_id)
        .having(func.count() > 1)
    )
    assert dup.all() == []

    # Limpieza para no afectar otras pruebas de temporada.
    for p in (await db.execute(select(Profile).filter(Profile.user_id == user.id))).scalars().all():
        p.is_active = False
    await db.commit()


@pytest.mark.asyncio
async def test_init_default_badges_concurrent_insert_is_swallowed(db: AsyncSession):
    # El seeding de badges por defecto debe seguir siendo idempotente aunque ya
    # existan los registros: no debe lanzar ni duplicar.
    await badge_service.init_default_badges(db)
    before = (
        await db.execute(select(func.count()).select_from(Badge))
    ).scalar_one()

    await badge_service.init_default_badges(db)
    after = (
        await db.execute(select(func.count()).select_from(Badge))
    ).scalar_one()

    assert after == before
