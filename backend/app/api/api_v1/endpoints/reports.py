from typing import Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.api.api_v1.endpoints.admin import check_admin
from app.core.redis_client import redis_client
import logging
from app.models.report import ReportStatus
from sqlalchemy import update
import json

logger = logging.getLogger(__name__)


router = APIRouter()


async def _affected_user_id(db: AsyncSession, report: models.Report) -> Optional[int]:
    """Resuelve el usuario afectado por un reporte: target_user, dueño del
    perfil reportado, o autor del comentario reportado."""
    if not report:
        return None
    if report.target_user_id:
        return report.target_user_id
    if report.target_profile_id:
        # Profile.user_id es nullable en el modelo; reportar el owner si existe.
        result = await db.execute(
            select(models.Profile.user_id).filter(models.Profile.id == report.target_profile_id)
        )
        return result.scalars().first()
    if report.target_comment_id:
        result = await db.execute(
            select(models.Comment.user_id).filter(models.Comment.id == report.target_comment_id)
        )
        return result.scalars().first()
    return None


async def _notify_user(db: AsyncSession, user_id: int, ntype: str, payload: dict, channel_key: str) -> None:
    notification = models.Notification(
        user_id=user_id,
        type=ntype,
        payload=payload,
        is_read=False,
    )
    db.add(notification)
    try:
        await db.commit()
        await db.refresh(notification)
    except Exception:
        db.rollback()
        logger.warning("Failed to persist notification to user %s", user_id, exc_info=True)
        return
    if redis_client:
        try:
            redis_client.publish(f"notifications:{user_id}", json.dumps({**payload, "type": ntype, "to_user_id": user_id}))
        except Exception:
            logger.warning("Failed to publish %s notification to user %s", ntype, user_id, exc_info=True)


def _same_target(report: models.Report, report_in: schemas.ReportCreate) -> bool:
    return (
        report.target_profile_id == report_in.target_profile_id
        and report.target_user_id == report_in.target_user_id
        and report.target_comment_id == report_in.target_comment_id
    )


@router.post("/", response_model=schemas.Report, status_code=status.HTTP_201_CREATED)
async def create_report(
    report_in: schemas.ReportCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    if not report_in.target_profile_id and not report_in.target_user_id and not report_in.target_comment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe especificar un perfil, usuario o comentario a reportar",
        )

    # Anti-duplicado: no permitir reportes activos (pendientes o en apelación)
    # del mismo reporter sobre el mismo objetivo.
    active_statuses = (ReportStatus.PENDING, ReportStatus.APPEALED)
    existing_result = await db.execute(
        select(models.Report)
        .filter(models.Report.reporter_id == current_user.id)
        .filter(models.Report.status.in_(active_statuses))
    )
    for existing in existing_result.scalars().all():
        if _same_target(existing, report_in):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya tienes un reporte activo sobre este objetivo",
            )

    db_obj = models.Report(
        reporter_id=current_user.id,
        target_profile_id=report_in.target_profile_id,
        target_user_id=report_in.target_user_id,
        target_comment_id=report_in.target_comment_id,
        reason=report_in.reason.strip(),
        description=(report_in.description or "").strip() or None,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)

    # Recargar con relaciones para poder serializar la respuesta (evita
    # lazy-loading asíncrono → MissingGreenlet).
    result = await db.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.reporter),
            selectinload(models.Report.target_profile),
            selectinload(models.Report.target_user),
            selectinload(models.Report.target_comment),
        )
        .where(models.Report.id == db_obj.id)
    )
    db_obj = result.scalars().first()
    
    # Notificar a administradores
    admins_result = await db.execute(select(models.User).filter(models.User.is_superuser == True))
    admins = admins_result.scalars().all()
    target_kind = (
        "comment" if db_obj.target_comment_id
        else "profile" if db_obj.target_profile_id
        else "user"
    )
    payload = {
        "report_id": db_obj.id,
        "reason": db_obj.reason,
        "target_kind": target_kind,
        "target_profile_id": db_obj.target_profile_id,
        "target_user_id": db_obj.target_user_id,
        "target_comment_id": db_obj.target_comment_id,
        "reporter_id": db_obj.reporter_id,
    }
    for admin in admins:
        try:
            notification = models.Notification(
                user_id=admin.id,
                type="new_report",
                payload=payload,
                is_read=False,
            )
            db.add(notification)
            await db.commit()
            await db.refresh(notification)
            if redis_client:
                redis_client.publish(f"notifications:{admin.id}", json.dumps({"type": "new_report", "payload": payload}))
        except Exception:
            logger.warning("Failed to publish new_report notification to admin %s", admin.id, exc_info=True)
    return db_obj


@router.get("/", response_model=List[schemas.Report])
async def list_reports(
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_async_db),
    admin_user: models.User = Depends(check_admin),
) -> Any:
    query = select(models.Report).options(
        selectinload(models.Report.reporter),
        selectinload(models.Report.target_profile),
        selectinload(models.Report.target_user),
        selectinload(models.Report.target_comment),
    )
    if status_filter:
        try:
            status_enum = ReportStatus(status_filter)
            query = query.filter(models.Report.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Estado de reporte inválido"
            )
    result = await db.execute(query.order_by(models.Report.created_at.desc()))
    return result.scalars().all()


@router.patch("/{report_id}", response_model=schemas.Report)
async def update_report_status(
    report_id: int,
    new_status: str,
    db: AsyncSession = Depends(get_async_db),
    admin_user: models.User = Depends(check_admin),
) -> Any:
    try:
        status_enum = ReportStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Estado de reporte inválido"
        )

    # El estado APPEALED solo lo fija el usuario afectado vía /appeal.
    if status_enum == ReportStatus.APPEALED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El estado de apelación solo puede establecerse mediante el flujo de apelación",
        )

    result = await db.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.reporter),
            selectinload(models.Report.target_profile),
            selectinload(models.Report.target_user),
            selectinload(models.Report.target_comment),
        )
        .filter(models.Report.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")

    values = {"status": status_enum}
    if report.status == ReportStatus.PENDING and status_enum != ReportStatus.PENDING:
        # El admin resuelve el reporte: registramos cuándo.
        values["resolved_at"] = datetime.now(timezone.utc)
    await db.execute(
        update(models.Report)
        .where(models.Report.id == report_id)
        .values(**values)
    )
    await db.commit()

    # Recargar con relaciones para poder serializar la respuesta (evita
    # lazy-loading asíncrono → MissingGreenlet tras el refresh).
    result = await db.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.reporter),
            selectinload(models.Report.target_profile),
            selectinload(models.Report.target_user),
            selectinload(models.Report.target_comment),
        )
        .filter(models.Report.id == report_id)
    )
    report = result.scalars().first()

    # Notificar al usuario afectado del desenlace del reporte.
    affected_id = await _affected_user_id(db, report)
    if affected_id and affected_id != admin_user.id:
        await _notify_user(
            db,
            affected_id,
            "report_resolved",
            {"report_id": report.id, "status": status_enum.value},
            "report_resolved",
        )
    return report


@router.post("/{report_id}/appeal", response_model=schemas.Report)
async def appeal_report(
    report_id: int,
    body: schemas.ReportAppeal,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    """
    El usuario afectado por un reporte (reportado) puede apelar una vez el
    desenlace. Restricciones:
      - Solo el usuario afectado (objetivo del reporte) puede apelar.
      - Solo una vez (el reporte pasa a estado APPEALED).
      - Solo si el reporte fue resuelto a favor del reporte (REVIEWED).
    """
    result = await db.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.target_profile),
            selectinload(models.Report.target_user),
            selectinload(models.Report.target_comment),
        )
        .filter(models.Report.id == report_id)
    )
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reporte no encontrado")

    affected_id = await _affected_user_id(db, report)
    if not affected_id or affected_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo el usuario reportado puede apelar este reporte",
        )

    if report.status != ReportStatus.REVIEWED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se puede apelar un reporte resuelto con acción (reviewed)",
        )

    reason = body.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="La razón de apelación es requerida")
    if len(reason) > 500:
        raise HTTPException(status_code=400, detail="La razón de apelación es demasiado larga")

    report.status = ReportStatus.APPEALED
    report.appeal_reason = reason
    report.appealed_at = datetime.now(timezone.utc)
    db.add(report)
    await db.commit()

    # Recargar con relaciones para poder serializar la respuesta (evita
    # lazy-loading asíncrono → MissingGreenlet tras el refresh).
    result = await db.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.reporter),
            selectinload(models.Report.target_profile),
            selectinload(models.Report.target_user),
            selectinload(models.Report.target_comment),
        )
        .filter(models.Report.id == report_id)
    )
    report = result.scalars().first()

    # Notificar a los administradores de la apelación.
    admins_result = await db.execute(select(models.User).filter(models.User.is_superuser == True))
    for admin in admins_result.scalars().all():
        await _notify_user(
            db,
            admin.id,
            "report_appealed",
            {"report_id": report.id, "appeal_reason": reason, "status": ReportStatus.APPEALED.value},
            "report_appealed",
        )
    return report
