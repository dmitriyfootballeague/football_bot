import os
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv

from football_bot.utils.config import DBConfig

load_dotenv(find_dotenv())


def _parse_allowed_tournaments(raw: str) -> set[str]:
    """Empty string → scrape all. Otherwise comma-separated tournament names."""
    if not raw.strip():
        return set()
    return {t.strip() for t in raw.split(",") if t.strip()}


@dataclass
class ScraperConfig:
    scrape_url: str = os.environ.get(
        "SCRAPE_URL",
        "https://olesports.ru/tournament/68fba38cd56d2ba191d6eaee",
    )
    sync_interval_hours: int = int(os.environ.get("SYNC_INTERVAL_HOURS", 6))
    # Comma-separated list of allowed tournament names; empty = scrape all.
    allowed_tournaments: set[str] = field(
        default_factory=lambda: _parse_allowed_tournaments(
            os.environ.get("SCRAPER_ALLOWED_TOURNAMENTS", "")
        )
    )
    # Exact club-page dropdown target or season template.
    # Examples:
    #   "Высший (Лига 8x8, 2025/2026)"
    #   "{division} (Лига 8x8, 2025/2026)"
    player_tournament: str | None = (
        os.environ.get("SCRAPER_PLAYER_TOURNAMENT", "").strip() or None
    )
