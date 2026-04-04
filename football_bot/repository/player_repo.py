from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from football_bot.models import Player, RegistrationStatus


class PlayerRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, player: Player) -> Player:
        self.session.add(player)
        await self.session.commit()
        await self.session.refresh(player)
        return player

    async def get_by_telegram_id(self, telegram_id: int) -> Player | None:
        stmt = (
            select(Player)
            .where(Player.telegram_id == telegram_id)
            .options(selectinload(Player.club))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, player_id: int) -> Player | None:
        stmt = (
            select(Player)
            .where(Player.id == player_id)
            .options(selectinload(Player.club))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_registrations(self) -> list[Player]:
        stmt = (
            select(Player)
            .where(Player.registration_status == RegistrationStatus.PENDING)
            .options(selectinload(Player.club))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_registration_status(
        self, player_id: int, status: RegistrationStatus
    ) -> None:
        stmt = (
            update(Player)
            .where(Player.id == player_id)
            .values(registration_status=status)
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def get_all_approved(self) -> list[Player]:
        stmt = select(Player).where(Player.registration_status == RegistrationStatus.APPROVED)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_rating_data(self, player_id: int, **kwargs) -> None:
        stmt = update(Player).where(Player.id == player_id).values(**kwargs)
        await self.session.execute(stmt)
        await self.session.commit()
