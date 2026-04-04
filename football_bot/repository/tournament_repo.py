from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.models import Tournament


class TournamentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Tournament]:
        stmt = select(Tournament).order_by(Tournament.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, tournament_id: int) -> Tournament | None:
        return await self.session.get(Tournament, tournament_id)

    async def upsert(self, name: str, external_id: str | None = None) -> Tournament:
        stmt = select(Tournament).where(Tournament.name == name)
        result = await self.session.execute(stmt)
        tournament = result.scalar_one_or_none()
        if tournament is None:
            tournament = Tournament(name=name, external_id=external_id)
            self.session.add(tournament)
            await self.session.commit()
            await self.session.refresh(tournament)
        elif external_id and not tournament.external_id:
            tournament.external_id = external_id
            await self.session.commit()
        return tournament
