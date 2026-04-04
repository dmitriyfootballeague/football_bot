from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery


class IsAdminFilter(Filter):
    async def __call__(self, event: Message | CallbackQuery, admin_ids: list) -> bool:
        user = event.from_user
        return user is not None and user.id in admin_ids


class IsLeagueAdminFilter(Filter):
    async def __call__(self, event: Message | CallbackQuery, league_admin_ids: list) -> bool:
        user = event.from_user
        return user is not None and user.id in league_admin_ids


class IsAnyAdminFilter(Filter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        admin_ids: list,
        league_admin_ids: list,
    ) -> bool:
        user = event.from_user
        return user is not None and user.id in set(admin_ids + league_admin_ids)
