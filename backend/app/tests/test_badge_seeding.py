import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.badge_service import badge_service
from app.models.badge import Badge


@pytest.mark.asyncio
async def test_init_default_badges_is_idempotent(db: AsyncSession):
    # Primera llamada: crea las badges por defecto.
    await badge_service.init_default_badges(db)

    result = await db.execute(select(Badge))
    first_count = len(result.scalars().all())

    # Segunda llamada: no debe duplicar ni lanzar IntegrityError.
    await badge_service.init_default_badges(db)

    result = await db.execute(select(Badge))
    second_count = len(result.scalars().all())

    assert first_count == second_count
    assert first_count > 0


@pytest.mark.asyncio
async def test_init_default_badges_tolerates_name_collision_different_slug(db: AsyncSession):
    # Simula el escenario de carrera: una badge con el MISMO nombre de una
    # por defecto pero con un slug distinto ya existe en la BD (la única
    # constraint violable es ix_badge_name). El seeding debe deduplicar por
    # nombre y no lanzar IntegrityError.
    existing = (await db.execute(select(Badge).filter(Badge.slug == "top-1"))).scalars().first()
    if existing is not None:
        await db.delete(existing)
        await db.commit()

    db.add(Badge(
        name="Top 1 Absoluto",      # collide con el nombre por defecto
        slug="top-1-manual",
        description="Existente manual",
        icon="👑",
        category="ranking",
        is_active=True,
    ))
    await db.commit()

    # No debe lanzar IntegrityError (antes: UniqueViolation en ix_badge_name).
    await badge_service.init_default_badges(db)

    result = await db.execute(select(Badge).filter(Badge.name == "Top 1 Absoluto"))
    rows = result.scalars().all()
    # Solo debe quedar una (la manual con slug distinto); la por defecto se
    # omite por colisión de nombre.
    assert len(rows) == 1
