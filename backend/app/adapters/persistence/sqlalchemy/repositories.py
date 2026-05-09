from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.profile import Profile
from app.models.vote import Vote


class SqlAlchemyProfileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_many_by_ids(self, ids: list[int]) -> list[Profile]:
        if not ids:
            return []
        result = await self._session.execute(select(Profile).filter(Profile.id.in_(ids)))
        return list(result.scalars().all())


class SqlAlchemyVoteRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def exists_for_pair(self, *, voter_id: int, a_id: int, b_id: int) -> bool:
        result = await self._session.execute(
            select(Vote.id).filter(
                Vote.voter_id == voter_id,
                or_(
                    (Vote.winner_id == a_id) & (Vote.loser_id == b_id),
                    (Vote.winner_id == b_id) & (Vote.loser_id == a_id),
                ),
            )
        )
        return result.scalar_one_or_none() is not None

    async def add(self, vote: Vote) -> None:
        self._session.add(vote)

    async def refresh(self, vote: Vote) -> None:
        await self._session.refresh(vote)
