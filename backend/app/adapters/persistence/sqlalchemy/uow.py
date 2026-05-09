from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.sqlalchemy.repositories import SqlAlchemyProfileRepository, SqlAlchemyVoteRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session: AsyncSession):
        self._session = session
        self.profiles = SqlAlchemyProfileRepository(session)
        self.votes = SqlAlchemyVoteRepository(session)

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
