from dataclasses import dataclass


@dataclass
class ScrapedPlayer:
    first_name: str
    last_name: str
    external_id: str
    team: str
    tournament: str
    games_played: int = 0
    mvp_count: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    # Site-provided rating (if available); 0.0 means not scraped yet
    rating: float = 0.0


@dataclass
class ScrapedTeam:
    name: str
    tournament: str
    tournament_external_id: str | None = None
    external_id: str | None = None
    club_url: str | None = None


@dataclass
class ScrapedTournament:
    name: str
    external_id: str
    url: str


# Chromium args to prevent crashes in Docker (limited /dev/shm)
BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-extensions",
    "--disable-background-networking",
    "--single-process",
    "--disable-setuid-sandbox",
]
