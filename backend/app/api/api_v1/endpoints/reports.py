from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.api.api_v1.endpoints.admin import check_admin
from app.core.redis_client import redis_client
import json


router = APIRouter()


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
            # Silenciar errores de notificación para no afectar creación de reporte
            pass
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
            from app.models.report import ReportStatus

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
    from app.models.report import ReportStatus
    from sqlalchemy import update

    try:
        status_enum = ReportStatus(new_status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Estado de reporte inválido"
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

    await db.execute(
        update(models.Report)
        .where(models.Report.id == report_id)
        .values(status=status_enum)
    )
    await db.commit()
    await db.refresh(report)
    return report
