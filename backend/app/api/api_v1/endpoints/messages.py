from typing import Any, List
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_, update

from app import models, schemas
from app.api import deps
from app.core.redis_client import redis_client
from app.core.moderation import validate_text


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


@router.get("/messages/threads", response_model=List[schemas.DirectMessageThread])
async def list_threads(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    unread_counts_result = await db.execute(
        select(models.DirectMessage.sender_id, func.count(models.DirectMessage.id))
        .filter(models.DirectMessage.recipient_id == current_user.id, models.DirectMessage.is_read == False)
        .group_by(models.DirectMessage.sender_id)
    )
    unread_counts = {row[0]: int(row[1]) for row in unread_counts_result.all()}

    result = await db.execute(
        select(models.DirectMessage)
        .filter(or_(models.DirectMessage.sender_id == current_user.id, models.DirectMessage.recipient_id == current_user.id))
        .order_by(models.DirectMessage.created_at.desc())
        .limit(200)
    )
    messages = result.scalars().all()

    threads: dict[int, schemas.DirectMessageThread] = {}
    for m in messages:
        other_id = m.recipient_id if m.sender_id == current_user.id else m.sender_id
        if other_id not in threads:
            threads[other_id] = schemas.DirectMessageThread(
                user_id=other_id,
                last_message=m,
                unread_count=unread_counts.get(other_id, 0),
            )
    return list(threads.values())


@router.get("/messages/{user_id}", response_model=List[schemas.DirectMessage])
async def list_messages(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _ensure_not_blocked(db, current_user.id, user_id)
    if limit <= 0:
        limit = 50
    if limit > 200:
        limit = 200
    result = await db.execute(
        select(models.DirectMessage)
        .filter(
            or_(
                and_(models.DirectMessage.sender_id == current_user.id, models.DirectMessage.recipient_id == user_id),
                and_(models.DirectMessage.sender_id == user_id, models.DirectMessage.recipient_id == current_user.id),
            )
        )
        .order_by(models.DirectMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/messages/{user_id}", response_model=schemas.DirectMessage, status_code=status.HTTP_201_CREATED)
async def send_message(
    user_id: int,
    payload: schemas.DirectMessageCreate,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No puedes enviarte mensajes a ti mismo")
    await _ensure_not_blocked(db, current_user.id, user_id)

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="El mensaje no puede estar vacío")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="El mensaje es demasiado largo")
    try:
        validate_text(content, fields=("mensaje",))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result_user = await db.execute(select(models.User).filter(models.User.id == user_id, models.User.is_active == True))
    target = result_user.scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    msg = models.DirectMessage(sender_id=current_user.id, recipient_id=user_id, content=content, is_read=False)
    db.add(msg)
    await db.flush()

    notification = models.Notification(
        user_id=user_id,
        type="direct_message",
        payload={"from_user_id": current_user.id, "message_id": msg.id},
    )
    db.add(notification)

    await db.commit()
    await db.refresh(msg)

    if redis_client:
        try:
            realtime_payload = {
                "type": "direct_message",
                "from_user_id": current_user.id,
                "to_user_id": user_id,
                "message_id": msg.id,
            }
            redis_client.publish(f"notifications:{user_id}", json.dumps(realtime_payload))
        except Exception:
            pass
    return msg


@router.post("/messages/{user_id}/mark-read")
async def mark_thread_read(
    user_id: int,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    await _ensure_not_blocked(db, current_user.id, user_id)
    await db.execute(
        update(models.DirectMessage)
        .where(
            models.DirectMessage.sender_id == user_id,
            models.DirectMessage.recipient_id == current_user.id,
            models.DirectMessage.is_read == False,
        )
        .values(is_read=True)
    )
    await db.commit()
    return {"detail": "ok"}

