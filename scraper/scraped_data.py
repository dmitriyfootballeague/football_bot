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
    position: str | None = None
    wins: int | None = None
    starts: int | None = None
    goals_conceded: int | None = None
    defensive_points: int | None = None
    # Site-provided rating (if available); 0.0 means not scraped yet
    rating: float = 0.0


@dataclass
class ScrapedMatchPlayerStat:
    match_external_id: str
    match_url: str
    tournament: str
    player_external_id: str
    player_name: str
    team_name: str
    opponent_name: str
    is_home: bool
    in_roster: bool
    started: bool
    mvp: bool
    team_goals: int
    opponent_goals: int
    goals_conceded: int
    team_won: bool
    match_date_label: str | None = None


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
