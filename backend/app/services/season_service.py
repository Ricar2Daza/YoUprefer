from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import Session
from sqlalchemy import func, update
from app.models.profile import Profile
from app.models.badge import Season, Badge, UserBadge
from app.models.user import User

class SeasonService:
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
