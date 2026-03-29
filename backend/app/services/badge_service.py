from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, desc
from app.models.badge import Badge, UserBadge
from app.models.profile import Profile
from app.models.user import User
from app.models.notification import Notification
from app.core.redis_client import redis_client
from fastapi.encoders import jsonable_encoder
import json
import logging

logger = logging.getLogger(__name__)


class BadgeService:
    async def get_all_badges(self, db: AsyncSession) -> List[Badge]:
        cache_key = "all_badges"

        if redis_client:
            try:
                cached = redis_client.get(cache_key)
                if cached:
                    badges_data = json.loads(cached)
                    return [Badge(**data) for data in badges_data]
            except Exception as e:
                logger.error(f"Redis error in get_all_badges: {e}")

        result = await db.execute(
            select(Badge)
            .filter(Badge.is_active == True)
            .order_by(Badge.min_position.asc().nulls_last())
        )
        badges = result.scalars().all()
        
        if redis_client:
            try:
                badges_data = jsonable_encoder(badges)
                redis_client.setex(cache_key, 3600, json.dumps(badges_data))
            except Exception as e:
                logger.error(f"Redis set error in get_all_badges: {e}")
            
        return badges

    async def get_user_badges(self, db: AsyncSession, user_id: int) -> List[UserBadge]:
        result = await db.execute(
            select(UserBadge)
            .options(select(UserBadge.badge)) # Eager load badge info
            .filter(UserBadge.user_id == user_id)
        )
        return result.scalars().all()

    async def get_best_rank(self, db: AsyncSession, user_id: int) -> Optional[int]:
        """Obtiene la mejor posición en el ranking de cualquiera de los perfiles del usuario"""
        # Cache best rank for short time? No, it changes frequently.
        subquery = (
            select(
                Profile.user_id,
                func.rank().over(order_by=desc(Profile.elo_score)).label("rank")
            )
            .filter(Profile.is_active == True, Profile.is_approved == True)
            .subquery()
        )
        
        query = select(func.min(subquery.c.rank)).filter(subquery.c.user_id == user_id)
        result = await db.execute(query)
        return result.scalar()

    async def check_and_award_badges(self, db: AsyncSession, user_id: int):
        """
        Verifica si el usuario merece nuevas badges basadas en sus perfiles y las asigna.
        """
        # 1. Obtener badges disponibles de tipo ranking
        # Use get_all_badges to leverage cache? 
        # But we need to filter by category='ranking'. 
        # Let's just query db or filter the cached result if we implemented cache properly.
        # For simplicity and consistency with transaction, query DB.
        ranking_badges_result = await db.execute(
            select(Badge).filter(Badge.category == "ranking", Badge.is_active == True)
        )
        ranking_badges = ranking_badges_result.scalars().all()
        
        if not ranking_badges:
            return

        # 2. Obtener perfiles del usuario
        user_profiles_result = await db.execute(
            select(Profile).filter(Profile.user_id == user_id, Profile.is_active == True)
        )
        user_profiles = user_profiles_result.scalars().all()

        if not user_profiles:
            return

        # 3. Calcular rankings de manera eficiente
        subquery = (
            select(
                Profile.id,
                func.rank().over(order_by=desc(Profile.elo_score)).label("rank")
            )
            .filter(Profile.is_active == True, Profile.is_approved == True)
            .subquery()
        )

        user_profile_ids = [p.id for p in user_profiles]
        
        ranks_query = select(subquery.c.id, subquery.c.rank).filter(subquery.c.id.in_(user_profile_ids))
        ranks_result = await db.execute(ranks_query)
        profile_ranks = {row.id: row.rank for row in ranks_result.all()}

        for profile in user_profiles:
            current_rank = profile_ranks.get(profile.id)

            if not current_rank:
                continue

            # 4. Verificar badges
            for badge in ranking_badges:
                if badge.min_position and current_rank <= badge.min_position:
                    # Verificar si ya tiene la badge
                    existing_badge_query = select(UserBadge).filter(
                        UserBadge.user_id == user_id,
                        UserBadge.badge_id == badge.id,
                    )
                    existing_badge = (await db.execute(existing_badge_query)).scalars().first()

                    if not existing_badge:
                        new_user_badge = UserBadge(
                            user_id=user_id,
                            badge_id=badge.id,
                            profile_id=profile.id,
                        )
                        db.add(new_user_badge)
                        
                        # Crear notificación
                        notification = Notification(
                            user_id=user_id,
                            type="badge_awarded",
                            payload={
                                "badge_id": badge.id,
                                "badge_name": badge.name,
                                "badge_icon": badge.icon,
                                "badge_slug": badge.slug,
                                "profile_id": profile.id
                            }
                        )
                        db.add(notification)
                        
                        await db.commit() # Commit inmediato para notificaciones realtime

    async def init_default_badges(self, db: AsyncSession):
        """Crea las badges por defecto si no existen"""
        defaults = [
            {
                "name": "Top 1 Absoluto",
                "slug": "top-1",
                "description": "Alcanza la posición #1 en el ranking global.",
                "icon": "👑",
                "category": "ranking",
                "level": "platino",
                "rarity": "legendary",
                "min_position": 1
            },
            {
                "name": "Podio de Honor",
                "slug": "top-3",
                "description": "Entra en el top 3 de mejores perfiles.",
                "icon": "🏆",
                "category": "ranking",
                "level": "platino",
                "rarity": "legendary",
                "min_position": 3
            },
            {
                "name": "Elite 5",
                "slug": "top-5",
                "description": "Posiciónate entre los 5 mejores.",
                "icon": "🌟",
                "category": "ranking",
                "level": "oro",
                "rarity": "epic",
                "min_position": 5
            },
            {
                "name": "Top 10",
                "slug": "top-10",
                "description": "Entra en el top 10 de mejores perfiles.",
                "icon": "🔥",
                "category": "ranking",
                "level": "oro",
                "rarity": "epic",
                "min_position": 10
            },
            {
                "name": "Top 25",
                "slug": "top-25",
                "description": "Entra en el top 25.",
                "icon": "💎",
                "category": "ranking",
                "level": "plata",
                "rarity": "rare",
                "min_position": 25
            },
            {
                "name": "Top 50",
                "slug": "top-50",
                "description": "Posiciónate entre los 50 mejores.",
                "icon": "💠",
                "category": "ranking",
                "level": "plata",
                "rarity": "rare",
                "min_position": 50
            },
            {
                "name": "Top 100",
                "slug": "top-100",
                "description": "Entra en el top 100.",
                "icon": "🏅",
                "category": "ranking",
                "level": "bronce",
                "rarity": "common",
                "min_position": 100
            },
            {
                "name": "Top 250",
                "slug": "top-250",
                "description": "Entra en el top 250.",
                "icon": "🥈",
                "category": "ranking",
                "level": "bronce",
                "rarity": "common",
                "min_position": 250
            },
            {
                "name": "Top 500",
                "slug": "top-500",
                "description": "Entra en el top 500.",
                "icon": "🥉",
                "category": "ranking",
                "level": "bronce",
                "rarity": "common",
                "min_position": 500
            },
            {
                "name": "En el Mapa (Top 1000)",
                "slug": "top-1000",
                "description": "Entra en el top 1000.",
                "icon": "📍",
                "category": "ranking",
                "level": "bronce",
                "rarity": "common",
                "min_position": 1000
            }
        ]

        for badge_data in defaults:
            exists = await db.execute(select(Badge).filter(Badge.slug == badge_data["slug"]))
            if not exists.scalars().first():
                db.add(Badge(**badge_data))
        
        await db.commit()

badge_service = BadgeService()
