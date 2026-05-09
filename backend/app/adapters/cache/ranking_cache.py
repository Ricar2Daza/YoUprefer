from app.application.ports.ranking_cache import RankingCachePort
from app.services.ranking_service import ranking_service


class RankingCacheAdapter(RankingCachePort):
    def invalidate(self) -> None:
        ranking_service.invalidate_ranking_cache()
