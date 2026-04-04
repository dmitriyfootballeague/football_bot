import asyncio

from football_bot.db import create_pool
from scraper.config import DBConfig, ScraperConfig
from scraper.logging import logger
from scraper.sync_service import SyncService


async def main():
    logger.info("Starting scraper service")

    db_config = DBConfig()
    scraper_config = ScraperConfig()

    session_pool = create_pool(db_config)
    sync_svc = SyncService(
        session_pool,
        scraper_config.scrape_url,
        allowed_tournaments=scraper_config.allowed_tournaments,
        player_tournament=scraper_config.player_tournament,
    )

    await sync_svc.start_periodic_sync(interval_hours=scraper_config.sync_interval_hours)


if __name__ == "__main__":
    asyncio.run(main())
