import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, func
from jose import jwt
from app.core.config import settings
from app.core.redis_client import redis_client
from app.api import deps
from app import models, schemas

router = APIRouter()


@router.websocket("/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """
    WebSocket de notificaciones.
    Requiere token JWT en query param: ?token=...
    """
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")
    except Exception:
        await websocket.close(code=1008)
        return

    if not redis_client:
        # Si Redis no está disponible, cerrar con código de política
        await websocket.close(code=1011)
        return

    pubsub = redis_client.pubsub()
    channel = f"notifications:{user_id}"
    pubsub.subscribe(channel)

    try:
        # Bucle principal: sondeo de pubsub no bloqueante
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and "data" in message:
                try:
                    data = message["data"]
                    if isinstance(data, (bytes, bytearray)):
                        data = data.decode("utf-8", errors="ignore")
                    await websocket.send_text(data)
                except Exception:
                    break
            else:
                # Pequeña espera para ceder el control y evitar alto uso de CPU
                await asyncio.sleep(0.3)
    except WebSocketDisconnect:
        pass
    except Exception:
        # Silenciar errores para no colapsar el servidor
        pass
    finally:
        try:
            pubsub.close()
        except Exception:
            pass


@router.get("/notifications", response_model=schemas.NotificationList)
async def list_my_notifications(
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
):
    q = select(models.Notification).filter(models.Notification.user_id == current_user.id)
    if unread_only:
        q = q.filter(models.Notification.is_read == False)
    q = q.order_by(models.Notification.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(q)
    items = result.scalars().all()

    count_q = select(func.count(models.Notification.id)).filter(models.Notification.user_id == current_user.id)
    if unread_only:
        count_q = count_q.filter(models.Notification.is_read == False)
    count_result = await db.execute(count_q)
    total = count_result.scalar() or 0

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.patch("/notifications/{notification_id}", response_model=schemas.Notification)
async def mark_notification_read(
    notification_id: int,
    payload: schemas.NotificationUpdate,
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
):
    result = await db.execute(
        select(models.Notification).filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
    )
    n = result.scalars().first()
    if not n:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")

    if payload.is_read is not None:
        n.is_read = payload.is_read

    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


@router.post("/notifications/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(deps.get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
):
    await db.execute(
        update(models.Notification)
        .where(models.Notification.user_id == current_user.id)
        .values(is_read=True)
    )
    await db.commit()
    return {"detail": "ok"}
