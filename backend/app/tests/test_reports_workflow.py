import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core import security
from app.core.config import settings
from app.models.user import User
from app.models.report import Report

AUTH = settings.API_V1_STR


async def _mkuser(db: AsyncSession, email: str, superuser: bool = False) -> User:
    u = User(
        email=email,
        hashed_password=security.get_password_hash("password123"),
        full_name=email.split("@")[0],
        is_active=True,
        is_superuser=superuser,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _login(client: AsyncClient, email: str, pw: str = "password123") -> dict:
    r = await client.post(
        f"{AUTH}/auth/login/access-token",
        data={"username": email, "password": pw},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _report_user(client: AsyncClient, reporter_hdrs: dict, target_uid: int) -> int:
    r = await client.post(
        f"{AUTH}/reports/",
        json={"target_user_id": target_uid, "reason": "spam"},
        headers=reporter_hdrs,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_reporte_flujo_completo_con_apelacion(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_flow_r@example.com")
    target = await _mkuser(db, "rep_flow_t@example.com")
    admin = await _mkuser(db, "rep_flow_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    target_hdrs = await _login(client, target.email)
    admin_hdrs = await _login(client, admin.email)

    # 1) Reporter crea el reporte
    report_id = await _report_user(client, reporter_hdrs, target.id)

    # 2) Admin lista reportes y lo revisa (resuelve a favor del reporte)
    r = await client.get(f"{AUTH}/reports/", headers=admin_hdrs)
    assert r.status_code == 200
    assert any(x["id"] == report_id for x in r.json())

    r = await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "reviewed"}, headers=admin_hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "reviewed"
    assert r.json()["resolved_at"] is not None

    # 3) El reportado apela exactamente una vez
    r = await client.post(f"{AUTH}/reports/{report_id}/appeal", json={"reason": "Falso positivo"}, headers=target_hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "appealed"
    assert r.json()["appeal_reason"] == "Falso positivo"
    assert r.json()["appealed_at"] is not None

    # 4) Segunda apelación rechazada
    r = await client.post(f"{AUTH}/reports/{report_id}/appeal", json={"reason": "otra vez"}, headers=target_hdrs)
    assert r.status_code == 400, r.text

    # 5) Admin decide tras apelación (desestima el reporte)
    r = await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "dismissed"}, headers=admin_hdrs)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_solo_el_reportado_puede_apelar(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_own_r@example.com")
    target = await _mkuser(db, "rep_own_t@example.com")
    stranger = await _mkuser(db, "rep_own_s@example.com")
    admin = await _mkuser(db, "rep_own_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    admin_hdrs = await _login(client, admin.email)
    stranger_hdrs = await _login(client, stranger.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)
    await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "reviewed"}, headers=admin_hdrs)

    # Un tercero no puede apelar
    r = await client.post(f"{AUTH}/reports/{report_id}/appeal", json={"reason": "no soy yo"}, headers=stranger_hdrs)
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_apelar_solo_estado_reviewed(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_st_r@example.com")
    target = await _mkuser(db, "rep_st_t@example.com")
    admin = await _mkuser(db, "rep_st_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    target_hdrs = await _login(client, target.email)
    admin_hdrs = await _login(client, admin.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)

    # PENDING: aún no se puede apelar
    r = await client.post(f"{AUTH}/reports/{report_id}/appeal", json={"reason": "muy pronto"}, headers=target_hdrs)
    assert r.status_code == 400, r.text

    # DISMISSED (no hubo acción): tampoco se puede apelar
    await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "dismissed"}, headers=admin_hdrs)
    r = await client.post(f"{AUTH}/reports/{report_id}/appeal", json={"reason": "desestimado"}, headers=target_hdrs)
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_admin_no_puede_fijar_estado_appealed(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_adm_r@example.com")
    target = await _mkuser(db, "rep_adm_t@example.com")
    admin = await _mkuser(db, "rep_adm_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    admin_hdrs = await _login(client, admin.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)

    r = await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "appealed"}, headers=admin_hdrs)
    assert r.status_code == 400, r.text
    assert "apelación" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reporte_duplicado_activo_rechazado(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_dup_r@example.com")
    target = await _mkuser(db, "rep_dup_t@example.com")

    reporter_hdrs = await _login(client, reporter.email)

    await _report_user(client, reporter_hdrs, target.id)
    r = await client.post(
        f"{AUTH}/reports/",
        json={"target_user_id": target.id, "reason": "spam otra vez"},
        headers=reporter_hdrs,
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_nuevo_reporte_tras_desestimacion(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_nd_r@example.com")
    target = await _mkuser(db, "rep_nd_t@example.com")
    admin = await _mkuser(db, "rep_nd_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    admin_hdrs = await _login(client, admin.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)
    # Objetivo queda desestimado: el reporter puede reportar de nuevo.
    await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "dismissed"}, headers=admin_hdrs)

    r = await client.post(
        f"{AUTH}/reports/",
        json={"target_user_id": target.id, "reason": "spam post"},
        headers=reporter_hdrs,
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_crear_reporte_requiere_objetivo(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_req_r@example.com")
    reporter_hdrs = await _login(client, reporter.email)

    r = await client.post(f"{AUTH}/reports/", json={"reason": "sin objetivo"}, headers=reporter_hdrs)
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_listar_reportes_filtra_por_estado(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_fil_r@example.com")
    target = await _mkuser(db, "rep_fil_t@example.com")
    admin = await _mkuser(db, "rep_fil_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    admin_hdrs = await _login(client, admin.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)
    await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "reviewed"}, headers=admin_hdrs)

    r = await client.get(f"{AUTH}/reports/?status_filter=reviewed", headers=admin_hdrs)
    assert r.status_code == 200
    reviewed = [x for x in r.json() if x["id"] == report_id]
    assert reviewed and reviewed[0]["status"] == "reviewed"

    r = await client.get(f"{AUTH}/reports/?status_filter=pending", headers=admin_hdrs)
    assert all(x["status"] == "pending" for x in r.json())

    r = await client.get(f"{AUTH}/reports/?status_filter=no_existe", headers=admin_hdrs)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_usuario_normal_no_lista_reportes(client: AsyncClient, db: AsyncSession):
    reporter = await _mkuser(db, "rep_for_r@example.com")
    reporter_hdrs = await _login(client, reporter.email)
    r = await client.get(f"{AUTH}/reports/", headers=reporter_hdrs)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_notificacion_al_reportado_al_resolver(client: AsyncClient, db: AsyncSession):
    from app.models.notification import Notification

    reporter = await _mkuser(db, "rep_not_r@example.com")
    target = await _mkuser(db, "rep_not_t@example.com")
    admin = await _mkuser(db, "rep_not_a@example.com", superuser=True)

    reporter_hdrs = await _login(client, reporter.email)
    admin_hdrs = await _login(client, admin.email)

    report_id = await _report_user(client, reporter_hdrs, target.id)
    await client.patch(f"{AUTH}/reports/{report_id}", params={"new_status": "reviewed"}, headers=admin_hdrs)

    # El reportado recibe una notificación report_resolved.
    result = await db.execute(
        select(Notification).filter(
            Notification.user_id == target.id,
            Notification.type == "report_resolved",
        )
    )
    notif = result.scalars().first()
    assert notif is not None
    assert notif.payload.get("report_id") == report_id