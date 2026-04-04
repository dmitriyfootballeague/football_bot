from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.models import Player
from football_bot.repository import PlayerRepository


class RatingService:
    def __init__(self, session: AsyncSession):
        self.repo = PlayerRepository(session)

    async def get_player_rating(self, telegram_id: int) -> Player | None:
        return await self.repo.get_by_telegram_id(telegram_id)

    async def update_rating(self, player_id: int, **rating_data) -> None:
        await self.repo.update_rating_data(player_id, **rating_data)
