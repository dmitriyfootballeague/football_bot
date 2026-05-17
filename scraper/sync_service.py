import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from scraper.league_scraper import LeagueScraper
from scraper.scraped_data import ScrapedPlayer
from football_bot.models import Club, Player, RegistrationStatus, ScrapedPlayerStats, Tournament
from scraper.logging import logger


def _compute_total_points(sp: ScrapedPlayer) -> float:
    """Synthetic rating: goals×3 + assists + MVP×2.

    Used when the site does not expose a numeric rating directly.
    Falls back to sp.rating if it was scraped from a rating column.
    """
    if sp.rating > 0:
        return sp.rating
    return sp.goals * 3 + sp.assists + sp.mvp_count * 2


def _compute_rankings(players: list[ScrapedPlayer]) -> dict[str, dict]:
    """Compute division_rank, division_total, avg_points_per_game, current_rating
    for every scraped player.  Returns a dict keyed by external_id."""
    by_tourn: dict[str, list[ScrapedPlayer]] = defaultdict(list)
    for sp in players:
        by_tourn[sp.tournament].append(sp)

    stats: dict[str, dict] = {}
    for tourn_players in by_tourn.values():
        sorted_div = sorted(tourn_players, key=_compute_total_points, reverse=True)
        div_total = len(sorted_div)
        for rank, sp in enumerate(sorted_div, start=1):
            total_pts = _compute_total_points(sp)
            games = max(sp.games_played, 1)
            avg = round(total_pts / games, 2)
            stats[sp.external_id] = {
                "current_rating": round(total_pts, 2),
                "division_rank": rank,
                "division_total": div_total,
                "avg_points_per_game": avg,
            }
    return stats


class SyncService:
    def __init__(
        self,
        session_pool: async_sessionmaker[AsyncSession],
        scrape_url: str,
        allowed_tournaments: set[str] | None = None,
        player_tournament: str | None = None,
    ):
        self.session_pool = session_pool
        self.scraper = LeagueScraper(
            scrape_url,
            allowed_tournaments=allowed_tournaments,
            player_tournament=player_tournament,
        )

    async def run_sync(self):
        """Run a single sync cycle: scrape website and update DB."""
        logger.info("Starting league data sync")
        tournaments = await self.scraper.scrape_tournaments()
        if not tournaments:
            logger.warning("No tournaments scraped, skipping DB update")
            return

        async with self.session_pool() as session:
            tournament_map = await self._upsert_tournaments_batch(session, tournaments)
            await session.commit()
            logger.info(f"Saved {len(tournament_map)} tournaments")

        teams = await self.scraper.scrape_teams(tournaments)
        if not teams:
            logger.warning("No clubs scraped after tournament sync")
            return

        teams_by_tournament: dict[str, list] = defaultdict(list)
        for team in teams:
            teams_by_tournament[team.tournament].append(team)

        total_current_players = 0
        total_prev_players = 0

        async with self.session_pool() as session:
            club_map = await self._upsert_clubs_batch(session, teams, tournament_map)
            await session.commit()
            logger.info(f"Saved {len(club_map)} clubs")

            now = datetime.now(timezone.utc)
            matched = 0
            prev_matched = 0
            saved = 0

            for tournament_name in sorted(teams_by_tournament):
                tournament_current_players: list[ScrapedPlayer] = []
                tournament_prev_players: list[ScrapedPlayer] = []
                tournament_saved = 0

                for team in teams_by_tournament[tournament_name]:
                    current_group, prev_group = await self.scraper.scrape_players_for_team(team)
                    tournament_current_players.extend(current_group)
                    tournament_prev_players.extend(prev_group)
                    total_current_players += len(current_group)
                    total_prev_players += len(prev_group)

                    club_saved = await self._save_scraped_players_batch(
                        session=session,
                        players=current_group,
                        club_map=club_map,
                    )
                    await session.commit()
                    tournament_saved += club_saved
                    saved += club_saved
                    logger.info(
                        f"Club '{team.name}' in tournament '{tournament_name}': "
                        f"{club_saved} scraped players saved"
                    )

                ranking_map = _compute_rankings(tournament_current_players)
                prev_ranking_map = _compute_rankings(tournament_prev_players)

                tournament_matched, tournament_prev_matched = await self._sync_registered_players_batch(
                    session=session,
                    current_players=tournament_current_players,
                    prev_players=tournament_prev_players,
                    ranking_map=ranking_map,
                    prev_ranking_map=prev_ranking_map,
                    now=now,
                )
                await session.commit()

                matched += tournament_matched
                prev_matched += tournament_prev_matched
                logger.info(
                    f"Tournament '{tournament_name}': "
                    f"{tournament_saved} scraped players saved, "
                    f"{tournament_matched} current matched, "
                    f"{tournament_prev_matched} previous matched"
                )

            logger.info(
                f"Sync completed: {len(tournaments)} tournaments, {len(teams)} teams, "
                f"{total_current_players} current players, {total_prev_players} previous players, "
                f"{saved} saved, {matched} current matched, {prev_matched} previous matched"
            )

    @staticmethod
    async def _upsert_tournaments_batch(
        session: AsyncSession,
        tournaments,
    ) -> dict[str, int]:
        payload: dict[str, str | None] = {}
        for tournament in tournaments:
            payload.setdefault(tournament.name, tournament.external_id)

        if not payload:
            return {}

        stmt = select(Tournament).where(Tournament.name.in_(list(payload.keys())))
        result = await session.execute(stmt)
        existing = {t.name: t for t in result.scalars().all()}

        for name, external_id in payload.items():
            tournament = existing.get(name)
            if tournament is None:
                tournament = Tournament(name=name, external_id=external_id)
                session.add(tournament)
                existing[name] = tournament
            elif external_id and not tournament.external_id:
                tournament.external_id = external_id

        await session.flush()
        return {name: tournament.id for name, tournament in existing.items()}

    @staticmethod
    async def _upsert_clubs_batch(
        session: AsyncSession,
        teams,
        tournament_map: dict[str, int],
    ) -> dict[tuple[str, str], int]:
        payload: dict[tuple[str, int], str | None] = {}
        for team in teams:
            tournament_id = tournament_map.get(team.tournament)
            if tournament_id is None:
                continue
            payload.setdefault((team.name, tournament_id), team.external_id)

        if not payload:
            return {}

        tournament_ids = {tournament_id for _, tournament_id in payload.keys()}
        stmt = select(Club).where(Club.tournament_id.in_(list(tournament_ids)))
        result = await session.execute(stmt)
        existing = {(club.name, club.tournament_id): club for club in result.scalars().all()}

        for (club_name, tournament_id), external_id in payload.items():
            club = existing.get((club_name, tournament_id))
            if club is None:
                club = Club(name=club_name, tournament_id=tournament_id, external_id=external_id)
                session.add(club)
                existing[(club_name, tournament_id)] = club
            elif external_id and not club.external_id:
                club.external_id = external_id

        await session.flush()

        club_map: dict[tuple[str, str], int] = {}
        for (club_name, tournament_id), club in existing.items():
            tournament_name = next(
                name for name, mapped_tournament_id in tournament_map.items()
                if mapped_tournament_id == tournament_id
            )
            club_map[(tournament_name, club_name)] = club.id
        return club_map

    @classmethod
    async def _save_scraped_players_batch(
        cls,
        session: AsyncSession,
        players: list[ScrapedPlayer],
        club_map: dict[tuple[str, str], int],
    ) -> int:
        saved = 0
        for sp in players:
            club_id = club_map.get((sp.tournament, sp.team))
            await cls._upsert_scraped_player(session, sp, club_id)
            saved += 1
        await session.flush()
        return saved

    @classmethod
    async def _sync_registered_players_batch(
        cls,
        session: AsyncSession,
        current_players: list[ScrapedPlayer],
        prev_players: list[ScrapedPlayer],
        ranking_map: dict[str, dict],
        prev_ranking_map: dict[str, dict],
        now: datetime,
    ) -> tuple[int, int]:
        matched = 0
        prev_matched = 0
        current_matched_players: list[Player] = []
        prev_matched_players: list[Player] = []

        for sp in current_players:
            db_player = await cls._find_registered_player(session, sp)
            if not db_player:
                continue

            computed = ranking_map.get(sp.external_id, {})
            cls._apply_current_player_data(
                db_player=db_player,
                scraped_player=sp,
                computed=computed,
                now=now,
            )
            current_matched_players.append(db_player)
            matched += 1

        cls._apply_position_ranks(current_matched_players, current=True)

        for sp in prev_players:
            db_player = await cls._find_registered_player(session, sp)
            if not db_player:
                continue

            computed = prev_ranking_map.get(sp.external_id, {})
            cls._apply_previous_player_data(
                db_player=db_player,
                computed=computed,
                now=now,
            )
            prev_matched_players.append(db_player)
            prev_matched += 1

        cls._apply_position_ranks(prev_matched_players, current=False)
        await session.flush()
        return matched, prev_matched

    @staticmethod
    async def _upsert_scraped_player(
        session: AsyncSession, sp: ScrapedPlayer, club_id: int | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        stmt = pg_insert(ScrapedPlayerStats).values(
            external_id=sp.external_id,
            first_name=sp.first_name,
            last_name=sp.last_name,
            club_id=club_id,
            games_played=sp.games_played,
            mvp_count=sp.mvp_count,
            goals=sp.goals,
            assists=sp.assists,
            yellow_cards=sp.yellow_cards,
            red_cards=sp.red_cards,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ScrapedPlayerStats.external_id],
            set_={
                "first_name": sp.first_name,
                "last_name": sp.last_name,
                "club_id": club_id,
                "games_played": sp.games_played,
                "mvp_count": sp.mvp_count,
                "goals": sp.goals,
                "assists": sp.assists,
                "yellow_cards": sp.yellow_cards,
                "red_cards": sp.red_cards,
                "updated_at": now,
            },
        )
        await session.execute(stmt)

    @staticmethod
    async def _find_registered_player(
        session: AsyncSession, sp: ScrapedPlayer,
    ) -> Player | None:
        stmt = select(Player).where(Player.external_id == sp.external_id)
        result = await session.execute(stmt)
        player = result.scalar_one_or_none()
        if player:
            return player

        stmt = select(Player).where(
            Player.first_name == sp.first_name,
            Player.last_name == sp.last_name,
            Player.club.has(Club.name == sp.team),
            Player.club.has(Club.tournament.has(Tournament.name == sp.tournament)),
        )
        result = await session.execute(stmt)
        players = list(result.scalars().all())
        if len(players) == 1:
            return players[0]

        stmt = select(Player).where(
            Player.first_name == sp.first_name,
            Player.last_name == sp.last_name,
        )
        result = await session.execute(stmt)
        players = list(result.scalars().all())
        if len(players) == 1:
            return players[0]
        return None

    @staticmethod
    def _apply_current_player_data(
        db_player: Player,
        scraped_player: ScrapedPlayer,
        computed: dict,
        now: datetime,
    ) -> None:
        if not db_player.external_id:
            db_player.external_id = scraped_player.external_id

        db_player.games_played = scraped_player.games_played
        db_player.mvp_count = scraped_player.mvp_count
        db_player.goals = scraped_player.goals
        db_player.assists = scraped_player.assists
        db_player.yellow_cards = scraped_player.yellow_cards
        db_player.red_cards = scraped_player.red_cards
        db_player.current_rating = computed.get("current_rating")
        db_player.division_rank = computed.get("division_rank")
        db_player.division_total = computed.get("division_total")
        db_player.avg_points_per_game = computed.get("avg_points_per_game")
        db_player.rating_updated_at = now

    @staticmethod
    def _apply_previous_player_data(
        db_player: Player,
        computed: dict,
        now: datetime,
    ) -> None:
        db_player.prev_season_rating = computed.get("current_rating")
        db_player.prev_division_rank = computed.get("division_rank")
        db_player.prev_division_total = computed.get("division_total")
        db_player.prev_position_rank = None
        db_player.prev_position_total = None
        db_player.prev_avg_points = computed.get("avg_points_per_game")
        db_player.prev_rating_updated_at = now

    @staticmethod
    def _apply_position_ranks(players: list[Player], current: bool) -> None:
        by_position: dict[object, list[Player]] = defaultdict(list)
        for player in players:
            if player.registration_status != RegistrationStatus.APPROVED or not player.position:
                continue
            by_position[player.position].append(player)

        for group in by_position.values():
            sorted_group = sorted(
                group,
                key=lambda player: (
                    player.current_rating if current else player.prev_season_rating
                ) or 0,
                reverse=True,
            )
            total = len(sorted_group)
            for rank, player in enumerate(sorted_group, start=1):
                if current:
                    player.position_rank = rank
                    player.position_total = total
                else:
                    player.prev_position_rank = rank
                    player.prev_position_total = total

    async def start_periodic_sync(self, interval_hours: int = 24):
        while True:
            try:
                await self.run_sync()
            except Exception as e:
                logger.error(f"Sync failed: {e}")
            await asyncio.sleep(interval_hours * 3600)
