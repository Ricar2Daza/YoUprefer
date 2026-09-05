import logging
from typing import Any, List, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import aliased

from app import models, schemas
from app.api import deps
from app.core import security
from app.core.redis_client import redis_client
from app.core.config import settings
from app.services.storage import storage_service
from app.core.moderation import validate_text
import uuid

logger = logging.getLogger(__name__)

router = APIRouter()


async def _build_self_user_response(
    db: AsyncSession, user: models.User, votes_count: int, badges: list
) -> schemas.User:
    follower_count, following_count = await _get_follow_counts(db, user.id)
    return schemas.User(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        bio=user.bio,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
        votes_cast_count=votes_count,
        badges=badges,
        follower_count=follower_count,
        following_count=following_count,
        mutual_following_count=0,
        is_online=True,
    )


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


async def _is_blocked(db: AsyncSession, a: int, b: int) -> bool:
    result = await db.execute(
        select(models.UserBlock.id).filter(
            or_(
                and_(models.UserBlock.blocker_id == a, models.UserBlock.blocked_id == b),
                and_(models.UserBlock.blocker_id == b, models.UserBlock.blocked_id == a),
            )
        )
    )
    return result.scalars().first() is not None


def _is_online(user_id: int) -> bool:
    if not redis_client:
        return False
    try:
        return bool(redis_client.get(f"online:{user_id}"))
    except Exception:
        logger.warning("Failed to check online status for user %s", user_id, exc_info=True)
        return False


from sqlalchemy.orm import aliased


async def _mutual_following_count(db: AsyncSession, a: int, b: int) -> int:
    f1 = models.Follow
    f2 = aliased(models.Follow)
    result = await db.execute(
        select(func.count(f1.following_id))
        .select_from(f1)
        .join(f2, and_(f1.following_id == f2.following_id))
        .filter(f1.follower_id == a, f2.follower_id == b)
    )
    return int(result.scalar() or 0)


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

    return await _build_self_user_response(db, current_user, votes_count, badges)


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
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(file_content) > max_bytes:
        raise HTTPException(status_code=413, detail=f"El archivo supera el límite de {settings.MAX_UPLOAD_SIZE_MB}MB")
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

    badges_rows = await db.execute(
        select(models.UserBadge, models.Badge, models.Season)
        .join(models.Badge, models.UserBadge.badge_id == models.Badge.id)
        .join(models.Season, models.UserBadge.season_id == models.Season.id)
        .filter(models.UserBadge.user_id == current_user.id)
    )
    badges = [
        schemas.UserBadgeBrief(name=b.name, icon=b.icon, season_name=s.name, profile_id=ub.profile_id)
        for ub, b, s in badges_rows.all()
    ]
    return await _build_self_user_response(db, current_user, votes_count, badges)


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
        update_data["hashed_password"] = security.get_password_hash(update_data.pop("password"))

    if "full_name" in update_data:
        try:
            validate_text(update_data.get("full_name"), fields=("nombre",))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    if "bio" in update_data:
        bio = update_data.get("bio")
        if bio is not None and len(bio) > 500:
            raise HTTPException(status_code=400, detail="La biografía es demasiado larga")
        try:
            validate_text(bio, fields=("biografía",))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
        schemas.UserBadgeBrief(name=b.name, icon=b.icon, season_name=s.name, profile_id=ub.profile_id)
        for ub, b, s in badges_rows.all()
    ]
    return await _build_self_user_response(db, current_user, votes_count, badges)


@router.get("/search", response_model=List[schemas.UserPublicProfile])
async def search_users(
    q: str,
    limit: int = 20,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    query = (q or "").strip()
    if not query:
        return []
    if limit <= 0:
        limit = 20
    if limit > 50:
        limit = 50
    result = await db.execute(
        select(models.User)
        .filter(models.User.is_active == True)
        .filter(or_(models.User.full_name.ilike(f"%{query}%"), models.User.email.ilike(f"%{query}%")))
        .limit(limit)
    )
    users = result.scalars().all()

    if not users:
        return []

    user_ids = [u.id for u in users]

    follower_result = await db.execute(
        select(models.Follow.following_id, func.count(models.Follow.id))
        .filter(models.Follow.following_id.in_(user_ids))
        .group_by(models.Follow.following_id)
    )
    follower_map = dict(follower_result.all())

    following_result = await db.execute(
        select(models.Follow.follower_id, func.count(models.Follow.id))
        .filter(models.Follow.follower_id.in_(user_ids))
        .group_by(models.Follow.follower_id)
    )
    following_map = dict(following_result.all())

    cv_count_result = await db.execute(
        select(models.CustomVote.owner_id, func.count(models.CustomVote.id))
        .filter(models.CustomVote.owner_id.in_(user_ids), models.CustomVote.is_active == True)
        .group_by(models.CustomVote.owner_id)
    )
    cv_map = dict(cv_count_result.all())

    block_pairs: set[tuple[int, int]] = set()
    if current_user:
        all_ids = user_ids + [current_user.id]
        block_result = await db.execute(
            select(models.UserBlock.blocker_id, models.UserBlock.blocked_id)
            .filter(models.UserBlock.blocker_id.in_(all_ids), models.UserBlock.blocked_id.in_(all_ids))
        )
        block_pairs = {(r.blocker_id, r.blocked_id) for r in block_result.all()}

    items: list[schemas.UserPublicProfile] = []
    for u in users:
        follower_count = follower_map.get(u.id, 0)
        following_count = following_map.get(u.id, 0)
        mutual = 0
        is_blocked_by_me = False
        has_blocked_me = False
        if current_user:
            is_blocked_by_me = (current_user.id, u.id) in block_pairs
            has_blocked_me = (u.id, current_user.id) in block_pairs

        items.append(
            schemas.UserPublicProfile(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                bio=u.bio,
                is_active=u.is_active,
                is_superuser=u.is_superuser,
                votes_cast_count=0,
                badges=[],
                follower_count=follower_count,
                following_count=following_count,
                mutual_following_count=mutual,
                is_online=_is_online(u.id),
                is_blocked_by_me=is_blocked_by_me,
                has_blocked_me=has_blocked_me,
                custom_votes_created_count=cv_map.get(u.id, 0),
            )
        )
    return items


@router.get("/{user_id}", response_model=schemas.UserPublicProfile)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    result = await db.execute(select(models.User).filter(models.User.id == user_id, models.User.is_active == True))
    u = result.scalars().first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    follower_count, following_count = await _get_follow_counts(db, u.id)
    mutual = 0
    is_blocked_by_me = False
    has_blocked_me = False
    if current_user:
        mutual = await _mutual_following_count(db, current_user.id, u.id)
        is_blocked_by_me = await _is_blocked(db, current_user.id, u.id)
        has_blocked_me = await _is_blocked(db, u.id, current_user.id)

    cv_count_result = await db.execute(select(func.count(models.CustomVote.id)).filter(models.CustomVote.owner_id == u.id, models.CustomVote.is_active == True))
    custom_votes_created_count = int(cv_count_result.scalar() or 0)

    return schemas.UserPublicProfile(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        avatar_url=u.avatar_url,
        bio=u.bio,
        is_active=u.is_active,
        is_superuser=u.is_superuser,
        votes_cast_count=0,
        badges=[],
        follower_count=follower_count,
        following_count=following_count,
        mutual_following_count=mutual,
        is_online=_is_online(u.id),
        is_blocked_by_me=is_blocked_by_me,
        has_blocked_me=has_blocked_me,
        custom_votes_created_count=custom_votes_created_count,
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
    if await _is_blocked(db, current_user.id, user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acción no permitida")

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
        except Exception as exc:
            logger.warning("Erro ao publicar notificação de novo seguidor", extra={"to_user_id": user_id, "error": str(exc)})

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


@router.get("/me/blocks", response_model=List[schemas.UserPublicProfile])
async def list_my_blocks(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    result = await db.execute(
        select(models.User)
        .join(models.UserBlock, models.UserBlock.blocked_id == models.User.id)
        .filter(models.UserBlock.blocker_id == current_user.id, models.User.is_active == True)
    )
    blocked_users = result.scalars().all()
    items: list[schemas.UserPublicProfile] = []
    for u in blocked_users:
        follower_count, following_count = await _get_follow_counts(db, u.id)
        items.append(
            schemas.UserPublicProfile(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                avatar_url=u.avatar_url,
                bio=u.bio,
                is_active=u.is_active,
                is_superuser=u.is_superuser,
                votes_cast_count=0,
                badges=[],
                follower_count=follower_count,
                following_count=following_count,
                mutual_following_count=0,
                is_online=_is_online(u.id),
                is_blocked_by_me=True,
                has_blocked_me=False,
                custom_votes_created_count=0,
            )
        )
    return items


@router.post("/{user_id}/block", response_model=schemas.UserBlock, status_code=status.HTTP_201_CREATED)
async def block_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes bloquearte a ti mismo")
    target_result = await db.execute(select(models.User).filter(models.User.id == user_id, models.User.is_active == True))
    target = target_result.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    existing_result = await db.execute(
        select(models.UserBlock).filter(models.UserBlock.blocker_id == current_user.id, models.UserBlock.blocked_id == user_id)
    )
    existing = existing_result.scalars().first()
    if existing:
        return existing

    block = models.UserBlock(blocker_id=current_user.id, blocked_id=user_id)
    db.add(block)

    await db.execute(
        select(models.Follow).filter(
            or_(
                and_(models.Follow.follower_id == current_user.id, models.Follow.following_id == user_id),
                and_(models.Follow.follower_id == user_id, models.Follow.following_id == current_user.id),
            )
        )
    )
    await db.execute(
        models.Follow.__table__.delete().where(
            or_(
                and_(models.Follow.follower_id == current_user.id, models.Follow.following_id == user_id),
                and_(models.Follow.follower_id == user_id, models.Follow.following_id == current_user.id),
            )
        )
    )

    await db.commit()
    await db.refresh(block)
    return block


@router.delete("/{user_id}/block")
async def unblock_user(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    result = await db.execute(
        select(models.UserBlock).filter(models.UserBlock.blocker_id == current_user.id, models.UserBlock.blocked_id == user_id)
    )
    block = result.scalars().first()
    if block:
        await db.delete(block)
        await db.commit()
    return {"detail": "unblocked"}


async def _build_user_list_with_counts(
    db: AsyncSession, users: list[models.User]
) -> list[schemas.User]:
    if not users:
        return []

    user_ids = [u.id for u in users]

    follower_result = await db.execute(
        select(models.Follow.following_id, func.count(models.Follow.id))
        .filter(models.Follow.following_id.in_(user_ids))
        .group_by(models.Follow.following_id)
    )
    follower_map = dict(follower_result.all())

    following_result = await db.execute(
        select(models.Follow.follower_id, func.count(models.Follow.id))
        .filter(models.Follow.follower_id.in_(user_ids))
        .group_by(models.Follow.follower_id)
    )
    following_map = dict(following_result.all())

    votes_result = await db.execute(
        select(models.Vote.voter_id, func.count(models.Vote.id))
        .filter(models.Vote.voter_id.in_(user_ids))
        .group_by(models.Vote.voter_id)
    )
    votes_map = dict(votes_result.all())

    return [
        schemas.User(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            avatar_url=u.avatar_url,
            is_active=u.is_active,
            is_superuser=u.is_superuser,
            votes_cast_count=votes_map.get(u.id, 0),
            follower_count=follower_map.get(u.id, 0),
            following_count=following_map.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/{user_id}/followers", response_model=List[schemas.User])
async def get_followers(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional_async),
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

    return await _build_user_list_with_counts(db, followers)


@router.get("/{user_id}/following", response_model=List[schemas.User])
async def get_following(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional_async),
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

    return await _build_user_list_with_counts(db, following_users)


@router.get("/{user_id}/follow-stats", response_model=schemas.FollowStats)
async def get_follow_stats(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional_async),
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
