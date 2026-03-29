from typing import Any, List
import json
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func

from app import models, schemas
from app.api import deps
from app.core.redis_client import redis_client
from app.services.storage import storage_service
import uuid

router = APIRouter()


async def _get_follow_counts(db: AsyncSession, user_id: int) -> tuple[int, int]:
    follower_result = await db.execute(
        select(func.count(models.Follow.id)).filter(models.Follow.following_id == user_id)
    )
    follower_count = follower_result.scalar() or 0

    following_result = await db.execute(
        select(func.count(models.Follow.id)).filter(models.Follow.follower_id == user_id)
    )
    following_count = following_result.scalar() or 0

    return follower_count, following_count


@router.get("/me", response_model=schemas.User)
async def read_user_me(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    result = await db.execute(
        select(func.count(models.Vote.id)).filter(models.Vote.voter_id == current_user.id)
    )
    votes_count = result.scalar() or 0

    badges_rows = await db.execute(
        select(models.UserBadge, models.Badge, models.Season)
        .join(models.Badge, models.UserBadge.badge_id == models.Badge.id)
        .join(models.Season, models.UserBadge.season_id == models.Season.id)
        .filter(models.UserBadge.user_id == current_user.id)
    )
    badges = [
        schemas.UserBadgeBrief(
            name=b.name,
            icon=b.icon,
            season_name=s.name,
            profile_id=ub.profile_id,
        )
        for ub, b, s in badges_rows.all()
    ]

    follower_count, following_count = await _get_follow_counts(db, current_user.id)

    return schemas.User(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        votes_cast_count=votes_count,
        badges=badges,
        follower_count=follower_count,
        following_count=following_count,
    )


@router.post("/me/avatar", response_model=schemas.User)
async def upload_user_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    """
    Subir o actualizar el avatar del usuario.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen")

    file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    object_name = f"avatars/{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    file_content = await file.read()
    success = storage_service.upload_file(file_content, object_name, file.content_type)
    
    if not success:
        raise HTTPException(status_code=500, detail="Error al subir la imagen")
        
    avatar_url = storage_service.get_public_url(object_name)
    current_user.avatar_url = avatar_url
    
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    # Recalcular contadores para devolver el objeto completo
    result = await db.execute(
        select(func.count(models.Vote.id)).filter(models.Vote.voter_id == current_user.id)
    )
    votes_count = result.scalar() or 0

    follower_count, following_count = await _get_follow_counts(db, current_user.id)
    
    # Badges (podemos devolver lista vacía por eficiencia o recalcular)
    # Por simplicidad recalculamos
    badges_rows = await db.execute(
        select(models.UserBadge, models.Badge, models.Season)
        .join(models.Badge, models.UserBadge.badge_id == models.Badge.id)
        .join(models.Season, models.UserBadge.season_id == models.Season.id)
        .filter(models.UserBadge.user_id == current_user.id)
    )
    badges = [
        schemas.UserBadgeBrief(
            name=b.name,
            icon=b.icon,
            season_name=s.name,
            profile_id=ub.profile_id,
        )
        for ub, b, s in badges_rows.all()
    ]

    return schemas.User(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        votes_cast_count=votes_count,
        badges=badges,
        follower_count=follower_count,
        following_count=following_count,
    )


@router.put("/me", response_model=schemas.User)
async def update_user_me(
    *,
    db: AsyncSession = Depends(deps.get_async_db),
    user_in: schemas.UserUpdate,
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    if user_in.email is not None:
        result = await db.execute(select(models.User).filter(models.User.email == user_in.email))
        existing_user = result.scalars().first()
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=400,
                detail="El usuario con este correo ya existe en el sistema.",
            )

    update_data = user_in.model_dump(exclude_unset=True)
    if update_data.get("password"):
        from app.core import security

        update_data["hashed_password"] = security.get_password_hash(update_data.pop("password"))

    for field, value in update_data.items():
        setattr(current_user, field, value)

    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    result = await db.execute(
        select(func.count(models.Vote.id)).filter(models.Vote.voter_id == current_user.id)
    )
    votes_count = result.scalar() or 0

    badges_rows = await db.execute(
        select(models.UserBadge, models.Badge, models.Season)
        .join(models.Badge, models.UserBadge.badge_id == models.Badge.id)
        .join(models.Season, models.UserBadge.season_id == models.Season.id)
        .filter(models.UserBadge.user_id == current_user.id)
    )
    badges = [
        schemas.UserBadgeBrief(
            name=b.name,
            icon=b.icon,
            season_name=s.name,
            profile_id=ub.profile_id,
        )
        for ub, b, s in badges_rows.all()
    ]

    follower_count, following_count = await _get_follow_counts(db, current_user.id)

    return schemas.User(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        avatar_url=current_user.avatar_url,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        votes_cast_count=votes_count,
        badges=badges,
        follower_count=follower_count,
        following_count=following_count,
    )


@router.get("/me/following-ids", response_model=schemas.FollowingIds)
async def get_my_following_ids(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    """
    Obtener lista de IDs de usuarios a los que el usuario actual sigue.
    Útil para pintar estados "Seguir/Dejar de seguir" en el frontend.
    """
    result = await db.execute(
        select(models.Follow.following_id).filter(models.Follow.follower_id == current_user.id)
    )
    ids = result.scalars().all()
    return {"following_ids": ids}


@router.post("/{user_id}/follow", response_model=schemas.Follow, status_code=status.HTTP_201_CREATED)
async def follow_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    """
    Seguir a un usuario.
    Idempotente: si ya lo sigues, devuelve la relación existente.
    """
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="No puedes seguirte a ti mismo")

    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    target_user = result.scalars().first()
    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    existing_result = await db.execute(
        select(models.Follow).filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.following_id == user_id,
        )
    )
    existing = existing_result.scalars().first()
    if existing:
        return existing

    follow = models.Follow(
        follower_id=current_user.id,
        following_id=user_id,
    )
    db.add(follow)
    await db.flush()

    notification = models.Notification(
        user_id=user_id,
        type="new_follower",
        payload={"from_user_id": current_user.id, "follow_id": follow.id},
    )
    db.add(notification)

    await db.commit()
    await db.refresh(follow)

    if redis_client:
        try:
            payload = {
                "type": "new_follower",
                "from_user_id": current_user.id,
                "to_user_id": user_id,
                "follow_id": follow.id,
            }
            redis_client.publish(f"notifications:{user_id}", json.dumps(payload))
        except Exception:
            pass

    return follow


@router.delete("/{user_id}/follow", status_code=status.HTTP_200_OK)
async def unfollow_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    """
    Dejar de seguir a un usuario.
    Idempotente: si no existe la relación, responde igualmente OK.
    """
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="No puedes dejar de seguirte a ti mismo")

    existing_result = await db.execute(
        select(models.Follow).filter(
            models.Follow.follower_id == current_user.id,
            models.Follow.following_id == user_id,
        )
    )
    follow = existing_result.scalars().first()
    if follow:
        await db.delete(follow)
        await db.commit()

    return {"detail": "unfollowed"}


@router.get("/{user_id}/followers", response_model=List[schemas.User])
async def get_followers(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    target_user = result.scalars().first()
    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    join_stmt = (
        select(models.User)
        .join(models.Follow, models.Follow.follower_id == models.User.id)
        .filter(models.Follow.following_id == user_id)
    )
    followers_result = await db.execute(join_stmt)
    followers = followers_result.scalars().all()

    users_with_counts: List[schemas.User] = []
    for u in followers:
        follower_count, following_count = await _get_follow_counts(db, u.id)
        votes_result = await db.execute(select(func.count(models.Vote.id)).filter(models.Vote.voter_id == u.id))
        votes_count = votes_result.scalar() or 0
        users_with_counts.append(
            schemas.User(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                is_active=u.is_active,
                is_superuser=u.is_superuser,
                votes_cast_count=votes_count,
                follower_count=follower_count,
                following_count=following_count,
            )
        )

    return users_with_counts


@router.get("/{user_id}/following", response_model=List[schemas.User])
async def get_following(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    target_user = result.scalars().first()
    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    join_stmt = (
        select(models.User)
        .join(models.Follow, models.Follow.following_id == models.User.id)
        .filter(models.Follow.follower_id == user_id)
    )
    following_result = await db.execute(join_stmt)
    following_users = following_result.scalars().all()

    users_with_counts: List[schemas.User] = []
    for u in following_users:
        follower_count, following_count = await _get_follow_counts(db, u.id)
        votes_result = await db.execute(select(func.count(models.Vote.id)).filter(models.Vote.voter_id == u.id))
        votes_count = votes_result.scalar() or 0
        users_with_counts.append(
            schemas.User(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                is_active=u.is_active,
                is_superuser=u.is_superuser,
                votes_cast_count=votes_count,
                follower_count=follower_count,
                following_count=following_count,
            )
        )

    return users_with_counts


@router.get("/{user_id}/follow-stats", response_model=schemas.FollowStats)
async def get_follow_stats(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    """
    Obtener estadísticas de seguidores/seguidos y relación mutua con el usuario actual (si hay sesión).
    """
    result = await db.execute(select(models.User).filter(models.User.id == user_id))
    target_user = result.scalars().first()
    if not target_user or not target_user.is_active:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    follower_count, following_count = await _get_follow_counts(db, user_id)

    is_following = False
    is_followed_by = False

    if current_user:
        rel_result = await db.execute(
            select(models.Follow).filter(
                models.Follow.follower_id == current_user.id,
                models.Follow.following_id == user_id,
            )
        )
        is_following = rel_result.scalars().first() is not None

        rel_back_result = await db.execute(
            select(models.Follow).filter(
                models.Follow.follower_id == user_id,
                models.Follow.following_id == current_user.id,
            )
        )
        is_followed_by = rel_back_result.scalars().first() is not None

    return {
        "user_id": user_id,
        "follower_count": follower_count,
        "following_count": following_count,
        "is_following": is_following,
        "is_followed_by": is_followed_by,
    }
