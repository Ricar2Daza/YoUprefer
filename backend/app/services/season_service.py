from datetime import datetime, timedelta, timezone
import json
import random
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy import func, update
from app.models.profile import Profile
from app.models.badge import Season, Badge, UserBadge
from app.models.user import User
from app.models.notification import Notification
from app.core.redis_client import redis_client

class SeasonService:
    async def ensure_season_current(self, db: AsyncSession) -> bool:
        current = await self.get_active_season(db)
        if not current:
            await self.start_new_season(db, "Initial Season")
            return False
        started_at = current.started_at
        if not started_at:
            return False
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        if started_at > datetime.now(timezone.utc) - timedelta(days=30):
            return False
        lock_key = "season:reset_lock"
        if redis_client:
            try:
                acquired = redis_client.set(lock_key, "1", nx=True, ex=300)
                if not acquired:
                    return False
            except Exception:
                pass
        await self.async_reset_rankings_and_award_badges(db, f"Season_{datetime.now().strftime('%Y_%m')}")
        return True

    async def get_active_season(self, db: AsyncSession) -> Season:
        result = await db.execute(select(Season).filter(Season.is_active == True))
        return result.scalars().first()

    def get_active_season_sync(self, db: Session) -> Optional[Season]:
        return db.query(Season).filter(Season.is_active == True).first()

    async def start_new_season(self, db: AsyncSession, name: str):
        active_season = await self.get_active_season(db)
        if active_season:
            active_season.is_active = False
            active_season.ended_at = datetime.utcnow()
            db.add(active_season)

        new_season = Season(name=name, is_active=True)
        db.add(new_season)
        await db.commit()
        await db.refresh(new_season)
        return new_season

    def start_new_season_sync(self, db: Session, name: str):
        active_season = self.get_active_season_sync(db)
        if active_season:
            active_season.is_active = False
            active_season.ended_at = datetime.utcnow()
            db.add(active_season)

        new_season = Season(name=name, is_active=True)
        db.add(new_season)
        db.commit()
        db.refresh(new_season)
        return new_season

    def reset_rankings_and_award_badges(self, db, season_name: str):
        """
        Otorga insignias al top 5 y reinicia a todos a 1200.
        Versión síncrona para tests (Session).
        """
        current_season = self.get_active_season_sync(db)
        if not current_season:
            current_season = self.start_new_season_sync(db, "Initial Season")

        top_profiles = (
            db.query(Profile)
            .filter(Profile.is_active == True, Profile.is_approved == True)
            .order_by(Profile.elo_score.desc())
            .limit(5)
            .all()
        )

        badge_gold = self._get_or_create_badge_sync(db, "Temporada Oro", "Top 1 en el ranking global", "👑")
        badge_silver = self._get_or_create_badge_sync(db, "Temporada Plata", "Top 2 en el ranking global", "🥈")
        badge_bronze = self._get_or_create_badge_sync(db, "Temporada Bronce", "Top 3 en el ranking global", "🥉")
        badges = [badge_gold, badge_silver, badge_bronze]

        for i, profile in enumerate(top_profiles):
            if i < len(badges):
                user_badge = UserBadge(
                    user_id=profile.user_id,
                    badge_id=badges[i].id,
                    profile_id=profile.id,
                    season_id=current_season.id
                )
                db.add(user_badge)

        db.execute(update(Profile).values(elo_score=1200))
        next_season_name = f"Season_{datetime.now().strftime('%Y_%m')}_{int(datetime.now().timestamp())}"
        self.start_new_season_sync(db, next_season_name)
        db.commit()
        return top_profiles

    async def async_reset_rankings_and_award_badges(self, db: AsyncSession, season_name: str):
        """
        Versión asíncrona para producción (AsyncSession).
        """
        current_season = await self.get_active_season(db)
        if not current_season:
            current_season = await self.start_new_season(db, "Initial Season")

        result_bottom = await db.execute(
            select(Profile)
            .filter(Profile.is_active == True, Profile.is_approved == True)
            .order_by(Profile.elo_score.asc())
            .limit(50)
        )
        bottom_profiles = result_bottom.scalars().all()

        result_top = await db.execute(
            select(Profile)
            .filter(Profile.is_active == True, Profile.is_approved == True)
            .order_by(Profile.elo_score.desc())
            .limit(5)
        )
        top_profiles = result_top.scalars().all()

        badge_gold = await self._get_or_create_badge(db, "Temporada Oro", "Top 1 en el ranking global", "👑")
        badge_silver = await self._get_or_create_badge(db, "Temporada Plata", "Top 2 en el ranking global", "🥈")
        badge_bronze = await self._get_or_create_badge(db, "Temporada Bronce", "Top 3 en el ranking global", "🥉")
        badges = [badge_gold, badge_silver, badge_bronze]

        for i, profile in enumerate(top_profiles):
            if i < len(badges):
                user_badge = UserBadge(
                    user_id=profile.user_id,
                    badge_id=badges[i].id,
                    profile_id=profile.id,
                    season_id=current_season.id
                )
                db.add(user_badge)

        tips = [
            "Probá luz natural cerca de una ventana y evitá el contraluz fuerte.",
            "Usá el modo retrato (o fondo desenfocado) para resaltar el sujeto.",
            "Limpiá la lente antes de sacar la foto: cambia muchísimo.",
            "Evitá zoom digital; acercate físicamente para mejor calidad.",
            "Buscá un fondo simple y ordenado para que la foto se vea más profesional.",
            "Alineá el horizonte y usá la grilla para encuadrar mejor.",
        ]
        for p in bottom_profiles:
            if not p.user_id:
                continue
            notification = Notification(
                user_id=p.user_id,
                type="motivation",
                payload={"tip": random.choice(tips), "season_id": current_season.id},
            )
            db.add(notification)
            if redis_client:
                try:
                    realtime_payload = {
                        "type": "motivation",
                        "to_user_id": p.user_id,
                        "tip": notification.payload["tip"],
                        "season_id": current_season.id,
                    }
                    redis_client.publish(f"notifications:{p.user_id}", json.dumps(realtime_payload))
                except Exception:
                    pass

        await db.execute(update(Profile).values(elo_score=1200))
        next_season_name = f"Season_{datetime.now().strftime('%Y_%m')}_{int(datetime.now().timestamp())}"
        await self.start_new_season(db, next_season_name)
        await db.commit()
        return top_profiles

    async def _get_or_create_badge(self, db: AsyncSession, name: str, desc: str, icon: str):
        result = await db.execute(select(Badge).filter(Badge.name == name))
        badge = result.scalars().first()
        if not badge:
            slug = name.lower().replace(" ", "-")
            badge = Badge(name=name, slug=slug, description=desc, icon=icon, category="ranking", is_active=True)
            db.add(badge)
            await db.commit()
            await db.refresh(badge)
        return badge

    def _get_or_create_badge_sync(self, db: Session, name: str, desc: str, icon: str):
        badge = db.query(Badge).filter(Badge.name == name).first()
        if not badge:
            slug = name.lower().replace(" ", "-")
            badge = Badge(name=name, slug=slug, description=desc, icon=icon, category="ranking", is_active=True)
            db.add(badge)
            db.commit()
            db.refresh(badge)
        return badge

season_service = SeasonService()
