from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, func

from app import models, schemas
from app.api import deps
from app.core.ratelimit import RateLimiter
from app.core.redis_client import redis_client
from app.core.config import settings
from app.core.moderation import validate_text
import logging
from app.services.storage import storage_service

logger = logging.getLogger(__name__)


router = APIRouter()


async def _ensure_not_blocked(db: AsyncSession, a: int, b: int) -> None:
    q = select(models.UserBlock.id).filter(
        or_(
            and_(models.UserBlock.blocker_id == a, models.UserBlock.blocked_id == b),
            and_(models.UserBlock.blocker_id == b, models.UserBlock.blocked_id == a),
        )
    )
    result = await db.execute(q)
    if result.scalars().first() is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acción no permitida")


async def _expire_and_notify_custom_votes(db: AsyncSession) -> None:
    now = datetime.now(timezone.utc)

    expiring_result = await db.execute(
        select(models.CustomVote)
        .filter(
            models.CustomVote.is_active == True,
            models.CustomVote.expires_at > now,
            models.CustomVote.expires_at <= now + timedelta(hours=24),
            models.CustomVote.expiring_notified == False,
        )
        .limit(200)
    )
    expiring = expiring_result.scalars().all()
    for v in expiring:
        v.expiring_notified = True
        db.add(v)
        participants_result = await db.execute(select(models.CustomVoteParticipant.user_id).filter(models.CustomVoteParticipant.vote_id == v.id))
        user_ids = set(participants_result.scalars().all())
        for uid in user_ids:
            n = models.Notification(
                user_id=uid,
                type="custom_vote_expiring",
                payload={"custom_vote_id": v.id, "expires_at": v.expires_at.isoformat()},
            )
            db.add(n)
            if redis_client:
                try:
                    redis_client.publish(
                        f"notifications:{uid}",
                        json.dumps({"type": "custom_vote_expiring", "to_user_id": uid, "custom_vote_id": v.id}),
                    )
                except Exception:
                    logger.warning("Failed to publish custom_vote_expiring notification to user %s", uid, exc_info=True)

    expired_result = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.is_active == True, models.CustomVote.expires_at <= now)
        .limit(200)
    )
    expired = expired_result.scalars().all()
    for v in expired:
        for p in v.participants:
            for photo in p.photos:
                if photo.object_name:
                    storage_service.delete_file(photo.object_name)
        await db.delete(v)
    if expiring or expired:
        await db.commit()


@router.get("/custom-votes/", response_model=List[schemas.CustomVote])
async def list_custom_votes(
    category_id: Optional[int] = None,
    owner_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    if limit <= 0:
        limit = 50
    if limit > 100:
        limit = 100
    q = (
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.is_active == True)
        .order_by(models.CustomVote.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if category_id:
        q = q.filter(models.CustomVote.category_id == category_id)
    if owner_id:
        q = q.filter(models.CustomVote.owner_id == owner_id)
    result = await db.execute(q)
    votes = result.scalars().unique().all()

    if current_user:
        filtered: list[models.CustomVote] = []
        for v in votes:
            participant_ids = [p.user_id for p in v.participants]
            blocked = False
            if participant_ids:
                res = await db.execute(
                    select(models.UserBlock.id).filter(
                        or_(
                            and_(models.UserBlock.blocker_id == current_user.id, models.UserBlock.blocked_id.in_(participant_ids)),
                            and_(models.UserBlock.blocked_id == current_user.id, models.UserBlock.blocker_id.in_(participant_ids)),
                        )
                    )
                )
                blocked = res.scalars().first() is not None
            if not blocked:
                filtered.append(v)
        return filtered
    return votes


@router.get("/custom-votes/me", response_model=List[schemas.CustomVote])
async def list_my_custom_votes(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    result = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.owner_id == current_user.id)
        .order_by(models.CustomVote.created_at.desc())
    )
    return result.scalars().unique().all()


@router.get("/custom-votes/{vote_id}", response_model=schemas.CustomVote)
async def get_custom_vote(
    vote_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    result = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.id == vote_id, models.CustomVote.is_active == True)
    )
    vote = result.scalars().unique().first()
    if not vote:
        raise HTTPException(status_code=404, detail="Votación no encontrada")
    if current_user:
        for p in vote.participants:
            await _ensure_not_blocked(db, current_user.id, p.user_id)
    return vote


@router.post(
    "/custom-votes/",
    response_model=schemas.CustomVote,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(RateLimiter(times=10, seconds=3600))],
)
async def create_custom_vote(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category_id: int = Form(...),
    challenged_user_id: Optional[int] = Form(None),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    title_clean = title.strip()
    if not title_clean:
        raise HTTPException(status_code=400, detail="El título es requerido")
    if len(title_clean) > 120:
        raise HTTPException(status_code=400, detail="Título demasiado largo")
    if description and len(description) > 2000:
        raise HTTPException(status_code=400, detail="Descripción demasiado larga")
    try:
        validate_text(title_clean, fields=("título",))
        validate_text(description, fields=("descripción",))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Debes subir al menos 1 foto")
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Máximo 8 fotos")

    category_result = await db.execute(select(models.Category).filter(models.Category.id == category_id, models.Category.is_active == True))
    category = category_result.scalars().first()
    if not category:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")

    expires_at = datetime.now(timezone.utc) + timedelta(days=5)
    vote = models.CustomVote(
        owner_id=current_user.id,
        category_id=category_id,
        title=title_clean,
        description=description.strip() if description else None,
        is_active=True,
        expires_at=expires_at,
        expiring_notified=False,
    )
    db.add(vote)
    await db.flush()

    owner_role = "challenger" if challenged_user_id else "owner"
    owner_participant = models.CustomVoteParticipant(vote_id=vote.id, user_id=current_user.id, role=owner_role)
    db.add(owner_participant)
    await db.flush()

    for f in files:
        if not (f.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Todas las fotos deben ser imágenes")
        ext = f.filename.split(".")[-1] if f.filename and "." in f.filename else "jpg"
        object_name = f"custom_votes/{current_user.id}/{uuid.uuid4()}.{ext}"
        content = await f.read()
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=f"El archivo {f.filename} supera el límite de {settings.MAX_UPLOAD_SIZE_MB}MB")
        ok = storage_service.upload_file(content, object_name, f.content_type or "image/jpeg")
        if not ok:
            raise HTTPException(status_code=500, detail="Error al subir una imagen")
        image_url = storage_service.get_public_url(object_name) or ""
        db.add(models.CustomVotePhoto(participant_id=owner_participant.id, image_url=image_url, object_name=object_name))

    challenged_participant = None
    if challenged_user_id:
        if challenged_user_id == current_user.id:
            raise HTTPException(status_code=400, detail="No puedes retarte a ti mismo")
        await _ensure_not_blocked(db, current_user.id, challenged_user_id)
        target_result = await db.execute(select(models.User).filter(models.User.id == challenged_user_id, models.User.is_active == True))
        target = target_result.scalars().first()
        if not target:
            raise HTTPException(status_code=404, detail="Usuario retado no encontrado")
        challenged_participant = models.CustomVoteParticipant(vote_id=vote.id, user_id=challenged_user_id, role="challenged")
        db.add(challenged_participant)
        n = models.Notification(
            user_id=challenged_user_id,
            type="challenge_received",
            payload={"custom_vote_id": vote.id, "from_user_id": current_user.id},
        )
        db.add(n)

    await db.commit()

    if challenged_user_id and redis_client:
        try:
            redis_client.publish(
                f"notifications:{challenged_user_id}",
                json.dumps({"type": "challenge_received", "to_user_id": challenged_user_id, "custom_vote_id": vote.id, "from_user_id": current_user.id}),
            )
        except Exception:
            logger.warning("Failed to publish challenge_received notification to user %s", challenged_user_id, exc_info=True)

    result_vote = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.id == vote.id)
    )
    return result_vote.scalars().unique().first()


@router.post("/custom-votes/{vote_id}/join", response_model=schemas.CustomVote)
async def join_challenge(
    vote_id: int,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="Debes subir al menos 1 foto")
    if len(files) > 8:
        raise HTTPException(status_code=400, detail="Máximo 8 fotos")

    vote_result = await db.execute(select(models.CustomVote).filter(models.CustomVote.id == vote_id, models.CustomVote.is_active == True))
    vote = vote_result.scalars().first()
    if not vote:
        raise HTTPException(status_code=404, detail="Votación no encontrada")

    participant_result = await db.execute(
        select(models.CustomVoteParticipant)
        .options(selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVoteParticipant.vote_id == vote_id, models.CustomVoteParticipant.user_id == current_user.id)
    )
    participant = participant_result.scalars().first()
    if not participant or participant.role != "challenged":
        raise HTTPException(status_code=403, detail="No tienes permiso para unirte a esta votación")

    if participant.photos:
        raise HTTPException(status_code=400, detail="Ya subiste tus fotos")

    owner_participant_result = await db.execute(
        select(models.CustomVoteParticipant).filter(models.CustomVoteParticipant.vote_id == vote_id, models.CustomVoteParticipant.role == "challenger")
    )
    owner_participant = owner_participant_result.scalars().first()
    if owner_participant:
        await _ensure_not_blocked(db, current_user.id, owner_participant.user_id)

    for f in files:
        if not (f.content_type or "").startswith("image/"):
            raise HTTPException(status_code=400, detail="Todas las fotos deben ser imágenes")
        ext = f.filename.split(".")[-1] if f.filename and "." in f.filename else "jpg"
        object_name = f"custom_votes/{current_user.id}/{uuid.uuid4()}.{ext}"
        content = await f.read()
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(status_code=413, detail=f"El archivo {f.filename} supera el límite de {settings.MAX_UPLOAD_SIZE_MB}MB")
        ok = storage_service.upload_file(content, object_name, f.content_type or "image/jpeg")
        if not ok:
            raise HTTPException(status_code=500, detail="Error al subir una imagen")
        image_url = storage_service.get_public_url(object_name) or ""
        db.add(models.CustomVotePhoto(participant_id=participant.id, image_url=image_url, object_name=object_name))

    await db.commit()

    # El participante ya fue cargado con selectinload(photos) (colección vacía) y
    # no expira al hacer commit (expire_on_commit=False), por lo que la re-consulta
    # devolvería una vista obsoleta sin las fotos recién subidas. Lo expiramos
    # para que la respuesta refleje las fotos persistidas.
    db.expire(participant)

    result_vote = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.id == vote_id)
    )
    return result_vote.scalars().unique().first()


@router.post(
    "/custom-votes/{vote_id}/vote",
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def vote_custom_vote(
    vote_id: int,
    payload: schemas.CustomVoteVoteRequest,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    vote_result = await db.execute(select(models.CustomVote).filter(models.CustomVote.id == vote_id, models.CustomVote.is_active == True))
    vote = vote_result.scalars().first()
    if not vote:
        raise HTTPException(status_code=404, detail="Votación no encontrada")
    now = datetime.now(timezone.utc)
    if vote.expires_at.tzinfo is None:
        expires_at = vote.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = vote.expires_at
    if expires_at <= now:
        raise HTTPException(status_code=400, detail="Esta votación ya expiró")

    photo_result = await db.execute(
        select(models.CustomVotePhoto, models.CustomVoteParticipant)
        .join(models.CustomVoteParticipant, models.CustomVotePhoto.participant_id == models.CustomVoteParticipant.id)
        .filter(models.CustomVotePhoto.id == payload.photo_id, models.CustomVoteParticipant.vote_id == vote_id)
    )
    row = photo_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    photo, participant = row[0], row[1]
    await _ensure_not_blocked(db, current_user.id, participant.user_id)

    existing_result = await db.execute(
        select(models.CustomVoteBallot).filter(models.CustomVoteBallot.vote_id == vote_id, models.CustomVoteBallot.voter_id == current_user.id)
    )
    existing = existing_result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Ya votaste en esta votación")

    ballot = models.CustomVoteBallot(vote_id=vote_id, voter_id=current_user.id, photo_id=photo.id)
    db.add(ballot)
    await db.commit()
    return {"detail": "ok"}


@router.get("/custom-votes/{vote_id}/results")
async def custom_vote_results(
    vote_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User | None = Depends(deps.get_current_user_optional_async),
) -> Any:
    await _expire_and_notify_custom_votes(db)
    vote_result = await db.execute(
        select(models.CustomVote)
        .options(selectinload(models.CustomVote.participants).selectinload(models.CustomVoteParticipant.photos))
        .filter(models.CustomVote.id == vote_id, models.CustomVote.is_active == True)
    )
    vote = vote_result.scalars().unique().first()
    if not vote:
        raise HTTPException(status_code=404, detail="Votación no encontrada")
    if current_user:
        for p in vote.participants:
            await _ensure_not_blocked(db, current_user.id, p.user_id)

    counts_result = await db.execute(
        select(models.CustomVoteBallot.photo_id, func.count(models.CustomVoteBallot.id))
        .filter(models.CustomVoteBallot.vote_id == vote_id)
        .group_by(models.CustomVoteBallot.photo_id)
    )
    photo_counts = {int(pid): int(c) for pid, c in counts_result.all()}

    user_counts: dict[int, int] = {}
    for p in vote.participants:
        total = 0
        for ph in p.photos:
            total += photo_counts.get(ph.id, 0)
        user_counts[p.user_id] = total

    return {
        "custom_vote_id": vote.id,
        "expires_at": vote.expires_at,
        "photo_counts": photo_counts,
        "user_counts": user_counts,
    }
