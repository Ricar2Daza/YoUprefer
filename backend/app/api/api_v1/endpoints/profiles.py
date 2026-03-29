from typing import List, Any, Optional
import json
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import aliased
from pydantic import BaseModel

from app import models, schemas
from app.api import deps
from app.api.deps import get_async_db
from app.models.profile import Profile, ProfileType, Gender
from app.models.comment import Comment
from app.services.storage import storage_service
from app.core.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

def _invalidate_ranking_cache():
    if redis_client:
        try:
            for key in redis_client.scan_iter("ranking:*"):
                redis_client.delete(key)
        except Exception:
            pass

def _invalidate_participation_cache(user_id: int):
    if redis_client:
        try:
            redis_client.delete(f"participation:{user_id}")
        except Exception:
            pass

@router.get("/pair", response_model=List[schemas.Profile])
async def get_random_pair(
    type: ProfileType = ProfileType.REAL,
    gender: Gender = Gender.FEMALE,
    category_id: Optional[int] = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional_async)
):
    """
    Obtener dos perfiles aleatorios del mismo tipo y género para comparar.
    """
    # Forzar tipo REAL por ahora según requerimientos
    type = ProfileType.REAL
    
    query = select(Profile).filter(
        Profile.type == type,
        Profile.gender == gender,
        Profile.is_active == True,
        Profile.is_approved == True
    )
    
    if category_id:
        query = query.filter(Profile.category_id == category_id)

    # Optimización: Obtener IDs candidatos
    import random
    
    # Obtener solo los IDs que cumplen los criterios
    # En async, seleccionamos solo la columna ID
    id_query = query.with_only_columns(Profile.id)
    cache_key = f"pair_candidates:{type}:{gender}:{category_id or 'none'}"
    candidate_ids = None
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                candidate_ids = json.loads(cached)
        except Exception:
            pass
    if not candidate_ids:
        result = await db.execute(id_query)
        candidate_ids = result.scalars().all()
        if redis_client and candidate_ids:
            try:
                redis_client.setex(cache_key, 30, json.dumps(candidate_ids))
            except Exception:
                pass
    
    if len(candidate_ids) < 2:
        raise HTTPException(status_code=404, detail="No hay suficientes perfiles para comparar")

    selected_ids = None

    if current_user:
        from app.models.vote import Vote

        id_set = set(candidate_ids)
        votes_rows = await db.execute(
            select(Vote.winner_id, Vote.loser_id).filter(Vote.voter_id == current_user.id)
        )
        voted_pairs = set()
        for w, l in votes_rows.all():
            if w in id_set and l in id_set and w != l:
                voted_pairs.add((w, l) if w < l else (l, w))

        total_pairs = len(candidate_ids) * (len(candidate_ids) - 1) // 2
        if total_pairs > 0 and len(voted_pairs) >= total_pairs:
            raise HTTPException(
                status_code=404,
                detail="¡No hay más emparejamientos para votar! Ya los has visto todos."
            )

        for _ in range(60):
            a, b = random.sample(candidate_ids, 2)
            pair = (a, b) if a < b else (b, a)
            if pair not in voted_pairs:
                selected_ids = [a, b]
                break

        if not selected_ids:
            raise HTTPException(
                status_code=404,
                detail="¡No hay más emparejamientos para votar! Ya los has visto todos."
            )
    else:
        selected_ids = random.sample(candidate_ids, 2)

    profiles_query = select(Profile).filter(Profile.id.in_(selected_ids))
    result = await db.execute(profiles_query)
    profiles = result.scalars().all()

    return profiles

@router.post("/", response_model=Any)
async def create_profile(
    profile_in: schemas.ProfileCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Crear un nuevo perfil real para el usuario actual.
    Devuelve una URL prefirmada para la subida de imagen.
    """
    if not profile_in.legal_consent:
        raise HTTPException(
            status_code=400, 
            detail="Se requiere consentimiento legal para participar"
        )

    existing_active = await db.execute(
        select(Profile.id).filter(
            Profile.user_id == current_user.id,
            Profile.is_active == True,
            or_(Profile.is_approved == True, Profile.is_approved == False) # Consideramos pendiente o aprobado
        )
    )
    if existing_active.scalars().first():
        raise HTTPException(
            status_code=400, 
            detail="Ya tienes un perfil activo o en proceso de aprobación. Solo se permite una foto por usuario."
        )
    
    # Generar nombre de archivo único
    import uuid
    file_extension = profile_in.image_extension or "jpg"
    object_name = f"profiles/{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    # Resolver categoría
    cat_id = profile_in.category_id
    if not cat_id:
        # Predeterminado a General
        from app.models.category import Category
        result = await db.execute(select(Category).filter(Category.slug == "general"))
        general = result.scalars().first()
        if general:
            cat_id = general.id

    # Crear perfil en BD
    db_obj = Profile(
        type=ProfileType.REAL,
        gender=profile_in.gender,
        image_url=storage_service.get_public_url(object_name) or "",
        user_id=current_user.id,
        category_id=cat_id,
        legal_consent=True,
        legal_consent_at=func.now(),
        is_approved=False
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    
    # Obtener URL prefirmada para el frontend
    upload_data = storage_service.get_presigned_url(object_name)
    
    if not upload_data:
         raise HTTPException(status_code=500, detail="No se pudo generar la URL de subida")

    try:
        logger.info(f"participation_status_changed user_id={current_user.id} profile_id={db_obj.id} action=create_pending")
    except Exception:
        pass
    return {
        "profile": jsonable_encoder(db_obj),
        "upload_url": upload_data
    }

@router.post("/upload-direct")
async def upload_profile_direct(
    file: UploadFile = File(...),
    gender: str = Form(...),
    legal_consent: bool = Form(...),
    category_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Endpoint de carga directa (para desarrollo/pruebas).
    Sube el archivo a R2 y crea el perfil en una sola solicitud.
    """
    from fastapi import UploadFile, File, Form
    
    if not legal_consent:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento legal")

    existing_active = await db.execute(
        select(Profile.id).filter(
            Profile.user_id == current_user.id,
            Profile.is_active == True
        )
    )
    if existing_active.scalars().first():
        raise HTTPException(
            status_code=400, 
            detail="Ya tienes un perfil activo. Solo se permite una foto por usuario."
        )
    
    # Generar nombre de archivo único
    import uuid
    file_extension = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    object_name = f"profiles/{current_user.id}_{uuid.uuid4()}.{file_extension}"
    
    # Subir a R2
    file_content = await file.read()
    success = storage_service.upload_file(file_content, object_name, file.content_type)
    
    if not success:
        raise HTTPException(status_code=500, detail="Error al subir la imagen")
    
    # Resolver categoría
    cat_id = category_id
    if not cat_id:
        # Predeterminado a General
        from app.models.category import Category
        result = await db.execute(select(Category).filter(Category.slug == "general"))
        general = result.scalars().first()
        if general:
            cat_id = general.id

    # Crear perfil
    db_obj = Profile(
        type=ProfileType.REAL,
        gender=Gender(gender),
        image_url=storage_service.get_public_url(object_name) or "",
        user_id=current_user.id,
        category_id=cat_id,
        legal_consent=True,
        legal_consent_at=func.now(),
        is_approved=True
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    _invalidate_ranking_cache()
    _invalidate_participation_cache(current_user.id)
    
    try:
        logger.info(f"participation_status_changed user_id={current_user.id} profile_id={db_obj.id} action=create_approved")
    except Exception:
        pass
    return {
        "id": db_obj.id,
        "type": db_obj.type,
        "gender": db_obj.gender,
        "image_url": db_obj.image_url,
        "elo_score": db_obj.elo_score,
        "is_approved": db_obj.is_approved,
        "message": "Perfil creado exitosamente"
    }

@router.get("/me", response_model=List[schemas.Profile])
async def get_my_profiles(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Obtener todos los perfiles del usuario actual.
    """
    result = await db.execute(select(Profile).filter(Profile.user_id == current_user.id))
    return result.scalars().all()

@router.get("/me/participation-status")
async def get_participation_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async)
):
    cache_key = f"participation:{current_user.id}"
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    result = await db.execute(
        select(Profile.id).filter(
            Profile.user_id == current_user.id,
            Profile.is_active == True,
            Profile.is_approved == True,
        )
    )
    active_id = result.scalars().first()
    data = {
        "participating": bool(active_id),
        "active_profile_id": active_id,
        "can_upload": not bool(active_id),
        "message": "Participando en el ranking" if active_id else "Sin foto activa en el ranking"
    }
    if redis_client:
        try:
            redis_client.setex(cache_key, 30, json.dumps(data))
        except Exception:
            pass
    return data

@router.get("/ranking", response_model=List[schemas.Profile])
async def get_ranking(
    type: ProfileType = ProfileType.REAL,
    gender: Gender = None,
    category_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Obtener los perfiles mejor calificados.
    """
    # Generación de clave de caché
    cache_key = f"ranking:{type}:{gender}:{category_id}:{limit}"
    
    # Intentar obtener de caché
    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            print(f"⚠️ Error de lectura en caché Redis: {e}")

    query = select(Profile).filter(
        Profile.type == type,
        Profile.is_active == True,
        Profile.is_approved == True
    )
    
    if gender:
        query = query.filter(Profile.gender == gender)
        
    if category_id:
        query = query.filter(Profile.category_id == category_id)
        
    query = query.order_by(Profile.elo_score.desc()).limit(limit)
    result = await db.execute(query)
    results = result.scalars().all()

    # Cachear resultados
    if redis_client:
        try:
            # Convertir objetos ORM a lista de dicts para serialización JSON
            data_to_cache = jsonable_encoder(results)
            redis_client.setex(cache_key, 60, json.dumps(data_to_cache))
        except Exception as e:
            print(f"⚠️ Error de escritura en caché Redis: {e}")
        
    return results

@router.post("/{id}/leave", response_model=schemas.Profile)
async def leave_game(
    *,
    db: AsyncSession = Depends(get_async_db),
    id: int,
    current_user: models.User = Depends(deps.get_current_user_async)
):
    result = await db.execute(select(Profile).filter(Profile.id == id))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")

    if profile.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=400, detail="Permisos insuficientes")

    profile.is_active = False
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    _invalidate_ranking_cache()
    _invalidate_participation_cache(profile.user_id)
    try:
        logger.info(f"participation_status_changed user_id={profile.user_id} profile_id={profile.id} action=leave")
    except Exception:
        pass
    return profile

@router.delete("/{id}", response_model=schemas.Profile)
async def delete_profile(
    *,
    db: AsyncSession = Depends(get_async_db),
    id: int,
    current_user: models.User = Depends(deps.get_current_user_async)
):
    """
    Eliminar un perfil.
    """
    result = await db.execute(select(Profile).filter(Profile.id == id))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")
        
    if profile.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=400, detail="Permisos insuficientes")
        
    await db.delete(profile)
    await db.commit()
    return profile


@router.get("/{id}/comments", response_model=List[schemas.Comment])
async def get_profile_comments(
    id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user: Optional[models.User] = Depends(deps.get_current_user_optional_async),
) -> Any:
    result = await db.execute(select(Profile).filter(Profile.id == id, Profile.is_active == True))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")

    comments_result = await db.execute(
        select(Comment).filter(Comment.profile_id == id).order_by(Comment.created_at.desc()).limit(50)
    )
    comments = comments_result.scalars().all()
    return comments


@router.post("/{id}/comments", response_model=schemas.Comment, status_code=status.HTTP_201_CREATED)
async def add_profile_comment(
    id: int,
    comment_in: schemas.CommentCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: models.User = Depends(deps.get_current_user_async),
) -> Any:
    result = await db.execute(select(Profile).filter(Profile.id == id, Profile.is_active == True))
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil no encontrado")

    content = comment_in.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="El comentario no puede estar vacío")
    if len(content) > 500:
        raise HTTPException(status_code=400, detail="El comentario es demasiado largo")

    db_obj = Comment(profile_id=id, user_id=current_user.id, content=content)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj
