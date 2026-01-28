from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.profile import Profile
from app.models.badge import Season, Badge, UserBadge
from app.models.user import User

class SeasonService:
    def get_active_season(self, db: Session) -> Season:
        return db.query(Season).filter(Season.is_active == True).first()

    def start_new_season(self, db: Session, name: str):
        # 1. Close current season
        active_season = self.get_active_season(db)
        if active_season:
            active_season.is_active = False
            active_season.ended_at = datetime.utcnow()
            db.add(active_season)

        # 2. Create new season
        new_season = Season(name=name, is_active=True)
        db.add(new_season)
        db.commit()
        db.refresh(new_season)
        return new_season

    def reset_rankings_and_award_badges(self, db: Session, season_name: str):
        """
        Awards badges to the top 5 and resets everyone to 1200.
        """
        # 1. Get current active season to associate badges
        current_season = self.get_active_season(db)
        if not current_season:
            current_season = self.start_new_season(db, "Initial Season")

        # 2. Find winners (Top 5)
        top_profiles = db.query(Profile).filter(Profile.is_active == True, Profile.is_approved == True)\
                         .order_by(Profile.elo_score.desc()).limit(5).all()

        # Ensure we have badges defined or create default ones
        badge_gold = self._get_or_create_badge(db, "Temporada Oro", "Top 1 en el ranking global", "👑")
        badge_silver = self._get_or_create_badge(db, "Temporada Plata", "Top 2 en el ranking global", "🥈")
        badge_bronze = self._get_or_create_badge(db, "Temporada Bronce", "Top 3 en el ranking global", "🥉")
        badge_top4 = self._get_or_create_badge(db, "Temporada Top 4", "Top 4 en el ranking global", "🏅")
        badge_top5 = self._get_or_create_badge(db, "Temporada Top 5", "Top 5 en el ranking global", "🏅")
        
        badges = [badge_gold, badge_silver, badge_bronze, badge_top4, badge_top5]

        for i, profile in enumerate(top_profiles):
            if i < len(badges):
                user_badge = UserBadge(
                    user_id=profile.user_id,
                    badge_id=badges[i].id,
                    profile_id=profile.id,
                    season_id=current_season.id
                )
                db.add(user_badge)

        # 3. Reset ALL ELO scores
        db.query(Profile).update({Profile.elo_score: 1200})
        
        # 4. Start next season
        # Logic to generate next season name (e.g. Month/Year)
        next_season_name = f"Season_{datetime.now().strftime('%Y_%m')}_{int(datetime.now().timestamp())}"
        self.start_new_season(db, next_season_name)

        db.commit()
        return top_profiles

    def _get_or_create_badge(self, db: Session, name: str, desc: str, icon: str):
        badge = db.query(Badge).filter(Badge.name == name).first()
        if not badge:
            badge = Badge(name=name, description=desc, icon=icon)
            db.add(badge)
            db.commit()
            db.refresh(badge)
        return badge

season_service = SeasonService()
