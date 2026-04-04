import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import Redis, RedisStorage

from football_bot.db import create_pool
from football_bot.handlers import commands
from football_bot.handlers.admin import admin_handlers, transfer_admin_handlers, admin_panel_handlers
from football_bot.handlers.user import (
    instruction_handler,
    rating_handlers,
    registration_handlers,
    transfer_handlers,
)
from football_bot.middlewares import DBSessionMiddleware
from football_bot.utils import BotConfig, DBConfig, RedisConfig, logger


async def main():
    logger.info("Starting football bot")

    bot_config = BotConfig()
    db_config = DBConfig()
    redis_config = RedisConfig()

    # Storage: Redis for production, Memory for local dev
    if redis_config.use_redis:
        redis = Redis(host=redis_config.host, port=redis_config.port, db=redis_config.db)
        storage = RedisStorage(redis=redis)
    else:
        storage = MemoryStorage()

    bot = Bot(
        token=bot_config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=storage)

    # Include routers (order matters: commands first for /start priority)
    dp.include_routers(
        commands.router,
        registration_handlers.router,
        instruction_handler.router,
        rating_handlers.router,
        transfer_handlers.router,
        admin_handlers.router,
        transfer_admin_handlers.router,
        admin_panel_handlers.router,
    )

    # DB session middleware
    session_pool = create_pool(db_config)
    dp.update.middleware(DBSessionMiddleware(session_pool=session_pool))

    # Pass admin IDs to handlers via workflow_data
    dp.workflow_data.update({
        "admin_ids": bot_config.admin_ids_to_list(),
        "league_admin_ids": bot_config.league_admin_ids_to_list(),
    })

    # Drop pending updates and start polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
