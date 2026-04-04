from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.models import Player, PlayerRole, PlayerPosition, RegistrationStatus
from football_bot.repository import PlayerRepository


class RegistrationService:
    def __init__(self, session: AsyncSession):
        self.repo = PlayerRepository(session)

    async def is_registered(self, telegram_id: int) -> bool:
        """Returns True only for PENDING or APPROVED players.

        REJECTED players are allowed to re-register, so this returns False for them.
        """
        player = await self.repo.get_by_telegram_id(telegram_id)
        if player is None:
            return False
        return player.registration_status in (
            RegistrationStatus.PENDING,
            RegistrationStatus.APPROVED,
        )

    async def get_player(self, telegram_id: int) -> Player | None:
        return await self.repo.get_by_telegram_id(telegram_id)

    async def create_registration(
        self,
        telegram_id: int,
        telegram_username: str | None,
        first_name: str,
        last_name: str,
        position: PlayerPosition,
        description: str | None,
        birth_date: date,
        photo_file_id: str,
        role: PlayerRole,
        club_id: int | None,
    ) -> Player:
        # If a rejected record exists, update it in-place (avoid unique constraint crash)
        existing = await self.repo.get_by_telegram_id(telegram_id)
        if existing and existing.registration_status == RegistrationStatus.REJECTED:
            await self.repo.update_rating_data(
                existing.id,
                telegram_username=telegram_username,
                first_name=first_name,
                last_name=last_name,
                position=position,
                description=description,
                birth_date=birth_date,
                photo_file_id=photo_file_id,
                role=role,
                club_id=club_id,
                registration_status=RegistrationStatus.PENDING,
            )
            return await self.repo.get_by_id(existing.id)

        player = Player(
            telegram_id=telegram_id,
            telegram_username=telegram_username,
            first_name=first_name,
            last_name=last_name,
            position=position,
            description=description,
            birth_date=birth_date,
            photo_file_id=photo_file_id,
            role=role,
            club_id=club_id,
            registration_status=RegistrationStatus.PENDING,
        )
        return await self.repo.create(player)

    async def get_pending(self) -> list[Player]:
        return await self.repo.get_pending_registrations()

    async def approve(self, player_id: int) -> None:
        await self.repo.update_registration_status(player_id, RegistrationStatus.APPROVED)

    async def reject(self, player_id: int) -> None:
        await self.repo.update_registration_status(player_id, RegistrationStatus.REJECTED)
