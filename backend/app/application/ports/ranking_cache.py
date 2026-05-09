from typing import Protocol


class RankingCachePort(Protocol):
    def invalidate(self) -> None: ...
