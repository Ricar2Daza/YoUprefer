from typing import Tuple, List, Optional
import json
from app.core.redis_client import redis_client

class RankingService:
    K_FACTOR = 32
    CACHE_KEY = "ranking_cache"
    CACHE_TTL = 60 * 5 # 5 minutes

    @staticmethod
    def invalidate_ranking_cache():
        if not redis_client:
            return
        try:
            for key in redis_client.scan_iter("ranking:*"):
                redis_client.delete(key)
        except Exception:
            pass

    @staticmethod
    def calculate_elo(winner_rating: int, loser_rating: int) -> Tuple[int, int]:
        """
        Calcula los nuevos puntajes ELO tanto para el ganador como para el perdedor.
        """
        expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
        expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

        new_winner_rating = round(winner_rating + RankingService.K_FACTOR * (1 - expected_winner))
        new_loser_rating = round(loser_rating + RankingService.K_FACTOR * (0 - expected_loser))

        RankingService.invalidate_ranking_cache()

        return new_winner_rating, new_loser_rating

    @staticmethod
    def get_cached_ranking(key: str) -> Optional[str]:
        if not redis_client:
            return None
        try:
            return redis_client.get(key)
        except Exception:
            return None

    @staticmethod
    def set_cached_ranking(key: str, data: str, ttl: int = 300):
        if not redis_client:
            return
        try:
            redis_client.setex(key, ttl, data)
        except Exception:
            pass

ranking_service = RankingService()
