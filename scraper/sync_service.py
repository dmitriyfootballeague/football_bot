import asyncio
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import column, select, table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from scraper.league_scraper import LeagueScraper, _extract_division_name
from scraper.player_position_overrides import get_fixed_player_position
from scraper.scraped_data import ScrapedMatchPlayerStat, ScrapedPlayer
from football_bot.models import (
    Club,
    MatchPlayerStats,
    Player,
    PlayerPosition,
    RegistrationStatus,
    ScrapedPlayerStats,
    ScrapedPlayerSeasonStats,
    Tournament,
)
from scraper.logging import logger


@dataclass(frozen=True)
class _PositionScoring:
    goal: int
    assist: int
    win: int
    start: int
    mvp: int
    defensive_base: int | None = None
    defensive_conceded_multiplier: int = 0


_SCORING_BY_POSITION = {
    PlayerPosition.FORWARD: _PositionScoring(goal=3, assist=3, win=1, start=1, mvp=1),
    PlayerPosition.ATTACKING_MIDFIELDER: _PositionScoring(
        goal=2,
        assist=3,
        win=1,
        start=1,
        mvp=1,
        defensive_base=4,
        defensive_conceded_multiplier=1,
    ),
    PlayerPosition.DEFENSIVE_MIDFIELDER: _PositionScoring(
        goal=2,
        assist=3,
        win=1,
        start=1,
        mvp=1,
        defensive_base=5,
        defensive_conceded_multiplier=1,
    ),
    PlayerPosition.DEFENDER: _PositionScoring(
        goal=1,
        assist=3,
        win=1,
        start=1,
        mvp=1,
        defensive_base=8,
        defensive_conceded_multiplier=2,
    ),
    PlayerPosition.GOALKEEPER: _PositionScoring(
        goal=0,
        assist=3,
        win=2,
        start=1,
        mvp=1,
        defensive_base=8,
        defensive_conceded_multiplier=2,
    ),
}

_SEASON_KEY_PATTERN = re.compile(r"(20\d{2})\s*/\s*(\d{2,4})")

_computed_ratings_view = table(
    "computed_scraped_player_ratings",
    column("id"),
    column("external_id"),
    column("season_key"),
    column("season_label"),
    column("season_bucket"),
    column("tournament_name"),
    column("division_key"),
    column("first_name"),
    column("last_name"),
    column("position"),
    column("club_id"),
    column("games_played"),
    column("mvp_count"),
    column("goals"),
    column("assists"),
    column("yellow_cards"),
    column("red_cards"),
    column("scraped_rating"),
    column("wins"),
    column("starts"),
    column("goals_conceded"),
    column("defensive_points"),
    column("current_rating"),
    column("division_rank"),
    column("division_total"),
    column("position_rank"),
    column("position_total"),
    column("avg_points_per_game"),
)


def _coerce_position(position: PlayerPosition | str | None) -> PlayerPosition | None:
    if isinstance(position, PlayerPosition):
        return position
    if not position:
        return None
    try:
        return PlayerPosition(position)
    except ValueError:
        return None


def _compute_total_points(sp: ScrapedPlayer) -> float:
    """Compute Scout points from fixed position and precomputed match aggregates.

    Defensive points must come from per-match aggregation. We do not reconstruct
    them from season-level goals conceded because that loses the per-match floor.
    """
    if sp.games_played <= 0:
        return 0

    position = _coerce_position(sp.position)
    scoring = _SCORING_BY_POSITION.get(position)
    if scoring is None:
        return sp.goals * 3 + sp.assists + sp.mvp_count * 2

    total = (
        sp.goals * scoring.goal
        + sp.assists * scoring.assist
        + (sp.wins or 0) * scoring.win
        + (sp.starts or 0) * scoring.start
        + sp.mvp_count * scoring.mvp
    )

    if sp.defensive_points is not None:
        total += max(sp.defensive_points, 0)

    return total


def _compute_match_defensive_points(
    position: PlayerPosition | str | None,
    goals_conceded: int,
    *,
    in_roster: bool,
) -> int:
    if not in_roster:
        return 0

    scoring = _SCORING_BY_POSITION.get(_coerce_position(position))
    if scoring is None or scoring.defensive_base is None:
        return 0

    return max(
        scoring.defensive_base - goals_conceded * scoring.defensive_conceded_multiplier,
        0,
    )


def _rating_group_key(tournament_name: str) -> str:
    division_name = _extract_division_name(tournament_name)
    if division_name:
        return division_name
    return tournament_name.strip()


def _season_label_for_player(player: ScrapedPlayer) -> str:
    return (player.season_label or player.tournament).strip()


def _season_key_for_label(label: str, season_bucket: str) -> str:
    normalized = label.strip()
    if not normalized:
        return season_bucket

    match = _SEASON_KEY_PATTERN.search(normalized)
    if not match:
        return normalized

    start_year = match.group(1)
    end_year = match.group(2)
    if len(end_year) == 2:
        end_year = f"{start_year[:2]}{end_year}"
    return f"{start_year}/{end_year}"


def _season_key_for_player(player: ScrapedPlayer) -> str:
    if player.season_key:
        return player.season_key
    return _season_key_for_label(_season_label_for_player(player), player.season_bucket)


def _resolve_tournament_season(players: list[ScrapedPlayer], tournament_name: str) -> tuple[str, str]:
    if not players:
        label = tournament_name
        return label, _season_key_for_label(label, "current")

    labels = [_season_label_for_player(player) for player in players if _season_label_for_player(player)]
    if not labels:
        label = tournament_name
    else:
        label = Counter(labels).most_common(1)[0][0]
    return label, _season_key_for_label(label, players[0].season_bucket)


def _compute_rankings(players: list[ScrapedPlayer]) -> dict[str, dict]:
    """Compute division_rank, division_total, avg_points_per_game, current_rating
    for every scraped player.  Returns a dict keyed by external_id."""
    by_tourn: dict[str, list[ScrapedPlayer]] = defaultdict(list)
    for sp in players:
        by_tourn[_rating_group_key(sp.tournament)].append(sp)

    stats: dict[str, dict] = {}
    for tourn_players in by_tourn.values():
        sorted_div = sorted(tourn_players, key=_compute_total_points, reverse=True)
        div_total = len(sorted_div)
        for rank, sp in enumerate(sorted_div, start=1):
            total_pts = _compute_total_points(sp)
            avg = round(total_pts / sp.games_played, 2) if sp.games_played > 0 else 0.0
            stats[sp.external_id] = {
                "current_rating": round(total_pts, 2),
                "division_rank": rank,
                "division_total": div_total,
                "avg_points_per_game": avg,
            }
    return stats


def _apply_match_stat_aggregates(
    players: list[ScrapedPlayer],
    match_stats: list[ScrapedMatchPlayerStat],
) -> None:
    by_player: dict[str, list[ScrapedMatchPlayerStat]] = defaultdict(list)
    for stat in match_stats:
        by_player[stat.player_external_id].append(stat)

    for player in players:
        player_match_stats = [
            stat for stat in by_player.get(player.external_id, []) if stat.in_roster
        ]
        if not player_match_stats:
            continue

        player.wins = sum(1 for stat in player_match_stats if stat.team_won)
        player.starts = sum(1 for stat in player_match_stats if stat.started)
        player.goals_conceded = sum(stat.goals_conceded for stat in player_match_stats)
        player.defensive_points = sum(
            _compute_match_defensive_points(
                player.position,
                stat.goals_conceded,
                in_roster=stat.in_roster,
            )
            for stat in player_match_stats
        )


def _resolve_club_id(
    club_map: dict[tuple[str, str], int],
    tournament_name: str,
    team_name: str,
) -> int | None:
    club_id = club_map.get((tournament_name, team_name))
    if club_id is not None:
        return club_id

    normalized_team_name = team_name.casefold()
    for (mapped_tournament, mapped_team), mapped_club_id in club_map.items():
        if (
            mapped_tournament == tournament_name
            and mapped_team.casefold() == normalized_team_name
        ):
            return mapped_club_id
    return None


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
        tournaments_by_name = {tournament.name: tournament for tournament in tournaments}

        total_current_players = 0
        total_prev_players = 0

        async with self.session_pool() as session:
            club_map = await self._upsert_clubs_batch(session, teams, tournament_map)
            await session.commit()
            logger.info(f"Saved {len(club_map)} clubs")

            now = datetime.now(timezone.utc)
            all_current_players: list[ScrapedPlayer] = []
            all_prev_players: list[ScrapedPlayer] = []
            matched = 0
            prev_matched = 0
            saved = 0
            season_saved = 0

            for tournament_name in sorted(teams_by_tournament):
                tournament_current_players: list[ScrapedPlayer] = []
                tournament_prev_players: list[ScrapedPlayer] = []
                tournament_saved = 0

                for team in teams_by_tournament[tournament_name]:
                    current_group, prev_group = await self.scraper.scrape_players_for_team(team)
                    self._apply_fixed_positions(current_group)
                    self._apply_fixed_positions(prev_group)
                    tournament_current_players.extend(current_group)
                    tournament_prev_players.extend(prev_group)
                    all_current_players.extend(current_group)
                    all_prev_players.extend(prev_group)
                    total_current_players += len(current_group)
                    total_prev_players += len(prev_group)

                    club_saved = await self._save_scraped_players_batch(
                        session=session,
                        players=current_group,
                        club_map=club_map,
                    )
                    club_season_saved = await self._save_scraped_player_season_stats_batch(
                        session=session,
                        players=current_group + prev_group,
                        club_map=club_map,
                    )
                    await session.commit()
                    tournament_saved += club_saved
                    saved += club_saved
                    season_saved += club_season_saved
                    logger.info(
                        f"Club '{team.name}' in tournament '{tournament_name}': "
                        f"{club_saved} current snapshots and {club_season_saved} season rows saved"
                    )

                match_stats: list[ScrapedMatchPlayerStat] = []
                tournament = tournaments_by_name.get(tournament_name)
                if tournament is not None:
                    season_label, season_key = _resolve_tournament_season(
                        tournament_current_players,
                        tournament_name,
                    )
                    match_stats = await self.scraper.scrape_match_stats_for_tournament(tournament)
                    match_rows_saved = await self._save_match_stats_batch(
                        session=session,
                        match_stats=match_stats,
                        tournament_id=tournament_map[tournament_name],
                        club_map=club_map,
                        season_key=season_key,
                        season_label=season_label,
                    )
                    await session.commit()
                    logger.info(
                        f"Tournament '{tournament_name}': "
                        f"{match_rows_saved} match player rows saved"
                    )

                logger.info(
                    f"Tournament '{tournament_name}': "
                    f"{tournament_saved} scraped players saved"
                )

            computed_ratings = await self._fetch_computed_ratings_batch(
                session=session,
                players=all_current_players + all_prev_players,
            )

            matched, prev_matched = await self._sync_registered_players_batch(
                session=session,
                current_players=all_current_players,
                prev_players=all_prev_players,
                computed_ratings=computed_ratings,
                now=now,
            )
            await session.commit()

            logger.info(
                f"Sync completed: {len(tournaments)} tournaments, {len(teams)} teams, "
                f"{total_current_players} current players, {total_prev_players} previous players, "
                f"{saved} current snapshots saved, {season_saved} season rows saved, "
                f"{matched} current matched, {prev_matched} previous matched"
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
    async def _save_scraped_player_season_stats_batch(
        cls,
        session: AsyncSession,
        players: list[ScrapedPlayer],
        club_map: dict[tuple[str, str], int],
    ) -> int:
        saved = 0
        for sp in players:
            club_id = club_map.get((sp.tournament, sp.team))
            await cls._upsert_scraped_player_season_stat(session, sp, club_id)
            saved += 1
        await session.flush()
        return saved

    @staticmethod
    async def _fetch_computed_ratings_batch(
        session: AsyncSession,
        players: list[ScrapedPlayer],
    ) -> dict[tuple[str, str], dict]:
        if not players:
            return {}

        external_ids = sorted({player.external_id for player in players})
        season_labels = sorted({_season_label_for_player(player) for player in players})
        stmt = (
            select(_computed_ratings_view)
            .where(_computed_ratings_view.c.external_id.in_(external_ids))
            .where(_computed_ratings_view.c.season_label.in_(season_labels))
        )
        result = await session.execute(stmt)
        rows = result.mappings().all() or []
        return {
            (row["external_id"], row["season_label"]): dict(row)
            for row in rows
        }

    @classmethod
    async def _save_match_stats_batch(
        cls,
        session: AsyncSession,
        match_stats: list[ScrapedMatchPlayerStat],
        tournament_id: int,
        club_map: dict[tuple[str, str], int],
        season_key: str | None,
        season_label: str | None,
    ) -> int:
        saved = 0
        for stat in match_stats:
            club_id = _resolve_club_id(club_map, stat.tournament, stat.team_name)
            await cls._upsert_match_player_stat(
                session,
                stat,
                tournament_id,
                club_id,
                season_key=season_key,
                season_label=season_label,
            )
            saved += 1
        await session.flush()
        return saved

    @staticmethod
    def _apply_fixed_positions(players: list[ScrapedPlayer]) -> None:
        for player in players:
            fixed_position = get_fixed_player_position(player.external_id)
            if fixed_position is not None:
                player.position = fixed_position.value

    @classmethod
    async def _sync_registered_players_batch(
        cls,
        session: AsyncSession,
        current_players: list[ScrapedPlayer],
        prev_players: list[ScrapedPlayer],
        computed_ratings: dict[tuple[str, str], dict],
        now: datetime,
    ) -> tuple[int, int]:
        matched = 0
        prev_matched = 0

        for sp in current_players:
            db_player = await cls._find_registered_player(session, sp)
            if not db_player:
                continue

            computed = cls._lookup_computed_rating(computed_ratings, sp)
            cls._apply_current_player_data(
                db_player=db_player,
                scraped_player=sp,
                computed=computed,
                now=now,
            )
            matched += 1

        for sp in prev_players:
            db_player = await cls._find_registered_player(session, sp)
            if not db_player:
                continue

            computed = cls._lookup_computed_rating(computed_ratings, sp)
            cls._apply_previous_player_data(
                db_player=db_player,
                scraped_player=sp,
                computed=computed,
                now=now,
            )
            prev_matched += 1

        await session.flush()
        return matched, prev_matched

    @staticmethod
    async def _upsert_scraped_player(
        session: AsyncSession,
        sp: ScrapedPlayer,
        club_id: int | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        values = {
            "external_id": sp.external_id,
            "first_name": sp.first_name,
            "last_name": sp.last_name,
            "position": _coerce_position(sp.position),
            "club_id": club_id,
            "games_played": sp.games_played,
            "mvp_count": sp.mvp_count,
            "goals": sp.goals,
            "assists": sp.assists,
            "yellow_cards": sp.yellow_cards,
            "red_cards": sp.red_cards,
            "updated_at": now,
        }
        update_values = {
            "first_name": sp.first_name,
            "last_name": sp.last_name,
            "position": _coerce_position(sp.position),
            "club_id": club_id,
            "games_played": sp.games_played,
            "mvp_count": sp.mvp_count,
            "goals": sp.goals,
            "assists": sp.assists,
            "yellow_cards": sp.yellow_cards,
            "red_cards": sp.red_cards,
            "updated_at": now,
        }

        stmt = pg_insert(ScrapedPlayerStats).values(
            **values,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ScrapedPlayerStats.external_id],
            set_=update_values,
        )
        await session.execute(stmt)

    @staticmethod
    async def _upsert_scraped_player_season_stat(
        session: AsyncSession,
        sp: ScrapedPlayer,
        club_id: int | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        season_label = _season_label_for_player(sp)
        position = _coerce_position(sp.position)
        values = {
            "external_id": sp.external_id,
            "season_key": _season_key_for_player(sp),
            "season_label": season_label,
            "season_bucket": sp.season_bucket,
            "tournament_name": sp.tournament,
            "first_name": sp.first_name,
            "last_name": sp.last_name,
            "position": position.value if position is not None else None,
            "club_id": club_id,
            "games_played": sp.games_played,
            "mvp_count": sp.mvp_count,
            "goals": sp.goals,
            "assists": sp.assists,
            "yellow_cards": sp.yellow_cards,
            "red_cards": sp.red_cards,
            "scraped_rating": sp.rating,
            "updated_at": now,
        }
        update_values = {
            "season_key": _season_key_for_player(sp),
            "season_bucket": sp.season_bucket,
            "tournament_name": sp.tournament,
            "first_name": sp.first_name,
            "last_name": sp.last_name,
            "position": position.value if position is not None else None,
            "club_id": club_id,
            "games_played": sp.games_played,
            "mvp_count": sp.mvp_count,
            "goals": sp.goals,
            "assists": sp.assists,
            "yellow_cards": sp.yellow_cards,
            "red_cards": sp.red_cards,
            "scraped_rating": sp.rating,
            "updated_at": now,
        }
        stmt = pg_insert(ScrapedPlayerSeasonStats).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_scraped_player_season_stats_external_id_season_label",
            set_=update_values,
        )
        await session.execute(stmt)

    @staticmethod
    async def _upsert_match_player_stat(
        session: AsyncSession,
        stat: ScrapedMatchPlayerStat,
        tournament_id: int,
        club_id: int | None,
        season_key: str | None,
        season_label: str | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        values = {
            "match_external_id": stat.match_external_id,
            "match_url": stat.match_url,
            "tournament_id": tournament_id,
            "club_id": club_id,
            "season_key": season_key,
            "season_label": season_label,
            "player_external_id": stat.player_external_id,
            "player_name": stat.player_name,
            "team_name": stat.team_name,
            "opponent_name": stat.opponent_name,
            "match_date_label": stat.match_date_label,
            "is_home": stat.is_home,
            "in_roster": stat.in_roster,
            "started": stat.started,
            "mvp": stat.mvp,
            "team_won": stat.team_won,
            "team_goals": stat.team_goals,
            "opponent_goals": stat.opponent_goals,
            "goals_conceded": stat.goals_conceded,
            "updated_at": now,
        }
        stmt = pg_insert(MatchPlayerStats).values(**values)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_match_stats_match_player",
            set_=values,
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
    def _lookup_computed_rating(
        computed_ratings: dict[tuple[str, str], dict],
        scraped_player: ScrapedPlayer,
    ) -> dict:
        return computed_ratings.get(
            (scraped_player.external_id, _season_label_for_player(scraped_player)),
            computed_ratings.get(scraped_player.external_id, {}),
        )

    @staticmethod
    def _apply_current_player_data(
        db_player: Player,
        scraped_player: ScrapedPlayer,
        computed: dict,
        now: datetime,
    ) -> None:
        if not db_player.external_id:
            db_player.external_id = scraped_player.external_id

        fixed_position = _coerce_position(scraped_player.position)
        if fixed_position is not None:
            db_player.position = fixed_position

        db_player.games_played = scraped_player.games_played
        db_player.mvp_count = scraped_player.mvp_count
        db_player.goals = scraped_player.goals
        db_player.assists = scraped_player.assists
        db_player.yellow_cards = scraped_player.yellow_cards
        db_player.red_cards = scraped_player.red_cards
        db_player.current_rating = computed.get("current_rating")
        db_player.division_rank = computed.get("division_rank")
        db_player.division_total = computed.get("division_total")
        db_player.position_rank = computed.get("position_rank")
        db_player.position_total = computed.get("position_total")
        db_player.avg_points_per_game = computed.get("avg_points_per_game")
        db_player.rating_updated_at = now

    @staticmethod
    def _apply_previous_player_data(
        db_player: Player,
        scraped_player: ScrapedPlayer,
        computed: dict,
        now: datetime,
    ) -> None:
        fixed_position = _coerce_position(scraped_player.position)
        if fixed_position is not None:
            db_player.position = fixed_position

        db_player.prev_season_rating = computed.get("current_rating")
        db_player.prev_division_rank = computed.get("division_rank")
        db_player.prev_division_total = computed.get("division_total")
        db_player.prev_position_rank = computed.get("position_rank")
        db_player.prev_position_total = computed.get("position_total")
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
