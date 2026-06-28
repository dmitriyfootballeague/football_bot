from playwright.async_api import async_playwright

from scraper.discovery import discover_tournaments
from scraper.logging import logger
from scraper.match_scraper import scrape_tournament_match_stats
from scraper.player_scraper import scrape_team_players
from scraper.scraped_data import (
    ScrapedMatchPlayerStat,
    ScrapedPlayer,
    ScrapedTeam,
    ScrapedTournament,
)
from scraper.team_scraper import scrape_tournament_teams


def _extract_division_name(tournament_name: str) -> str | None:
    if "—" in tournament_name:
        division = tournament_name.split("—", 1)[1].strip()
        return division or None
    if " - " in tournament_name:
        division = tournament_name.split(" - ", 1)[1].strip()
        return division or None
    return None


def _resolve_player_tournament(team_tournament: str, configured_target: str | None) -> str | None:
    if not configured_target:
        return None

    division = _extract_division_name(team_tournament)
    if not division:
        return configured_target

    if "{division}" in configured_target:
        return configured_target.format(division=division)

    bracket_idx = configured_target.find("(")
    if bracket_idx != -1:
        suffix = configured_target[bracket_idx:].strip()
        return f"{division} {suffix}"

    return configured_target


class LeagueScraper:
    """Scrapes team and player data from olesports.ru (Amateum platform).

    The site is a React SPA — Playwright renders JS before extracting data.
    Flow:
      1. Visit tournament page → discover tournament tabs (div.navi-group spans)
      2. Click each tournament tab → collect teams for that tournament
      3. Visit each club page → parse div.team-players for player stats
    """

    def __init__(
        self,
        base_url: str,
        allowed_tournaments: set[str] | None = None,
        player_tournament: str | None = None,
    ):
        self.base_url = base_url
        # None or empty set → scrape all tournaments found on page
        self.allowed_tournaments = allowed_tournaments or set()
        self.player_tournament = player_tournament

    async def scrape_tournaments(self):
        async with async_playwright() as pw:
            allowed = self.allowed_tournaments if self.allowed_tournaments else None
            tournaments = await discover_tournaments(pw, self.base_url, allowed=allowed)
            logger.info(f"Found {len(tournaments)} tournaments: {[d.name for d in tournaments]}")
            return tournaments

    async def scrape_teams(self, tournaments):
        teams: list[ScrapedTeam] = []

        async with async_playwright() as pw:
            for tourn in tournaments:
                try:
                    tourn_teams = await scrape_tournament_teams(pw, tourn)
                    teams.extend(tourn_teams)
                    logger.info(f"Tournament '{tourn.name}': {len(tourn_teams)} teams")
                except Exception as e:
                    logger.error(f"Failed to scrape tournament '{tourn.name}': {e}")

        return teams

    async def scrape_players_for_teams(
        self, teams: list[ScrapedTeam],
    ) -> tuple[list[ScrapedPlayer], list[ScrapedPlayer]]:
        current_players: list[ScrapedPlayer] = []
        previous_players: list[ScrapedPlayer] = []

        async with async_playwright() as pw:
            for team in teams:
                team_current, team_previous = await self._scrape_players_for_team_with_pw(pw, team)
                current_players.extend(team_current)
                previous_players.extend(team_previous)

        return current_players, previous_players

    async def scrape_players_for_team(
        self, team: ScrapedTeam,
    ) -> tuple[list[ScrapedPlayer], list[ScrapedPlayer]]:
        async with async_playwright() as pw:
            return await self._scrape_players_for_team_with_pw(pw, team)

    async def scrape_match_stats_for_tournament(
        self, tournament: ScrapedTournament,
    ) -> list[ScrapedMatchPlayerStat]:
        async with async_playwright() as pw:
            return await scrape_tournament_match_stats(pw, tournament)

    async def _scrape_players_for_team_with_pw(
        self, pw, team: ScrapedTeam,
    ) -> tuple[list[ScrapedPlayer], list[ScrapedPlayer]]:
        current_players: list[ScrapedPlayer] = []
        previous_players: list[ScrapedPlayer] = []

        if not team.club_url:
            return current_players, previous_players

        try:
            target_tournament = _resolve_player_tournament(
                team.tournament,
                self.player_tournament,
            )
            current_players = await scrape_team_players(
                pw,
                team.club_url,
                team.name,
                team.tournament,
                season_bucket="current",
                target_tournament=target_tournament,
            )
            logger.info(f"  {team.name}: {len(current_players)} current-season players scraped")
        except Exception as e:
            logger.error(f"  Failed to scrape current season for {team.name}: {e}")

        try:
            previous_players = await scrape_team_players(
                pw, team.club_url, team.name, team.tournament, season_bucket="previous",
            )
            logger.info(
                f"  {team.name}: {len(previous_players)} previous-season players scraped"
            )
        except Exception as e:
            logger.error(f"  Failed to scrape previous season for {team.name}: {e}")

        return current_players, previous_players

    async def scrape_all(self) -> tuple[list[ScrapedTeam], list[ScrapedPlayer], list[ScrapedPlayer]]:
        tournaments = await self.scrape_tournaments()
        teams = await self.scrape_teams(tournaments)
        current_players, previous_players = await self.scrape_players_for_teams(teams)
        logger.info(
            f"Scraping complete: {len(tournaments)} tournaments, "
            f"{len(teams)} teams, {len(current_players)} current players, "
            f"{len(previous_players)} previous players"
        )
        return teams, current_players, previous_players
