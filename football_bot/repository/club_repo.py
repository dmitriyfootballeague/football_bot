from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from football_bot.models import Club


class ClubRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[Club]:
        stmt = select(Club).options(selectinload(Club.tournament))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_tournament_id(self, tournament_id: int) -> list[Club]:
        stmt = select(Club).where(Club.tournament_id == tournament_id).order_by(Club.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, club_id: int) -> Club | None:
        stmt = (
            select(Club)
            .where(Club.id == club_id)
            .options(selectinload(Club.tournament))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_from_scrape(
        self, name: str, tournament_id: int, external_id: str | None = None
    ) -> Club:
        stmt = select(Club).where(Club.name == name, Club.tournament_id == tournament_id)
        result = await self.session.execute(stmt)
        club = result.scalar_one_or_none()
        if club is None:
            club = Club(name=name, tournament_id=tournament_id, external_id=external_id)
            self.session.add(club)
            await self.session.commit()
            await self.session.refresh(club)
        return club

    async def update_name(self, club_id: int, new_name: str) -> None:
        stmt = update(Club).where(Club.id == club_id).values(name=new_name)
        await self.session.execute(stmt)
        await self.session.commit()
