import re
from datetime import datetime

from sqlalchemy import column, desc, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from football_bot.models import (
    Club,
    Player,
    ScrapedPlayerSeasonStats,
    Tournament,
)


_SEASON_KEY_PATTERN = re.compile(r"(20\d{2})\s*/\s*(\d{2,4})")

_computed_ratings_view = table(
    "computed_scraped_player_ratings",
    column("external_id"),
    column("season_key"),
    column("season_label"),
    column("season_bucket"),
    column("current_rating"),
    column("division_rank"),
    column("division_total"),
    column("position_rank"),
    column("position_total"),
    column("avg_points_per_game"),
)


def _season_key_from_label(label: str, season_bucket: str) -> str:
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


class SeasonRatingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def apply_rating_override(
        self,
        player: Player,
        *,
        season_bucket: str,
        rating: float,
        updated_at: datetime,
    ) -> bool:
        season_row = await self._get_or_create_season_row(player, season_bucket)
        if season_row is None:
            return False

        season_row.rating_override = rating
        season_row.rating_override_updated_at = updated_at
        await self.session.flush()

        await self._sync_players_from_view(
            season_key=season_row.season_key,
            season_bucket=season_bucket,
            updated_at=updated_at,
        )

        await self.session.commit()
        return True

    async def _get_or_create_season_row(
        self,
        player: Player,
        season_bucket: str,
    ) -> ScrapedPlayerSeasonStats | None:
        if not player.external_id:
            return None

        stmt = (
            select(ScrapedPlayerSeasonStats)
            .where(ScrapedPlayerSeasonStats.external_id == player.external_id)
            .where(ScrapedPlayerSeasonStats.season_bucket == season_bucket)
            .order_by(desc(ScrapedPlayerSeasonStats.updated_at), desc(ScrapedPlayerSeasonStats.id))
        )
        result = await self.session.execute(stmt)
        rows = list(result.scalars().all())
        if rows:
            return rows[0]

        season_label = await self._infer_season_label(player, season_bucket)
        if not season_label:
            return None

        tournament_name = await self._infer_tournament_name(player)
        row = ScrapedPlayerSeasonStats(
            external_id=player.external_id,
            season_key=_season_key_from_label(season_label, season_bucket),
            season_label=season_label,
            season_bucket=season_bucket,
            tournament_name=tournament_name or season_label,
            first_name=player.first_name,
            last_name=player.last_name,
            position=player.position.value if player.position else None,
            club_id=player.club_id,
            games_played=0,
            mvp_count=0,
            goals=0,
            assists=0,
            yellow_cards=0,
            red_cards=0,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def _infer_season_label(
        self,
        player: Player,
        season_bucket: str,
    ) -> str | None:
        stmt = (
            select(ScrapedPlayerSeasonStats.season_label)
            .where(ScrapedPlayerSeasonStats.season_bucket == season_bucket)
            .order_by(desc(ScrapedPlayerSeasonStats.updated_at), desc(ScrapedPlayerSeasonStats.id))
        )
        result = await self.session.execute(stmt)
        labels = list(result.scalars().all())
        if labels:
            return labels[0]

        tournament_name = await self._infer_tournament_name(player)
        if tournament_name:
            return tournament_name

        return None

    async def _infer_tournament_name(self, player: Player) -> str | None:
        if not player.club_id:
            return None

        stmt = (
            select(Tournament.name)
            .select_from(Club)
            .join(Tournament, Tournament.id == Club.tournament_id)
            .where(Club.id == player.club_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _sync_players_from_view(
        self,
        *,
        season_key: str,
        season_bucket: str,
        updated_at: datetime,
    ) -> None:
        stmt = (
            select(_computed_ratings_view)
            .where(_computed_ratings_view.c.season_key == season_key)
            .where(_computed_ratings_view.c.season_bucket == season_bucket)
        )
        result = await self.session.execute(stmt)
        rows = result.mappings().all() or []
        if not rows:
            return

        external_ids = [row["external_id"] for row in rows]
        player_stmt = select(Player).where(Player.external_id.in_(external_ids))
        player_result = await self.session.execute(player_stmt)
        players_by_external_id = {
            player.external_id: player
            for player in player_result.scalars().all()
            if player.external_id
        }

        for row in rows:
            player = players_by_external_id.get(row["external_id"])
            if player is None:
                continue

            if season_bucket == "current":
                player.current_rating = row["current_rating"]
                player.division_rank = row["division_rank"]
                player.division_total = row["division_total"]
                player.position_rank = row["position_rank"]
                player.position_total = row["position_total"]
                player.avg_points_per_game = row["avg_points_per_game"]
                player.rating_updated_at = updated_at
            else:
                player.prev_season_rating = row["current_rating"]
                player.prev_division_rank = row["division_rank"]
                player.prev_division_total = row["division_total"]
                player.prev_position_rank = row["position_rank"]
                player.prev_position_total = row["position_total"]
                player.prev_avg_points = row["avg_points_per_game"]
                player.prev_rating_updated_at = updated_at

        await self.session.flush()
