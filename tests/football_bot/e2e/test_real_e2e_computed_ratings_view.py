from sqlalchemy import column, select, table

import pytest

from football_bot.models import MatchPlayerStats, PlayerPosition, ScrapedPlayerSeasonStats
from tests.football_bot.e2e.support import _seed_tournament_and_club


pytestmark = pytest.mark.e2e

_computed_ratings_view = table(
    "computed_scraped_player_ratings",
    column("external_id"),
    column("season_label"),
    column("goals_conceded"),
    column("defensive_points"),
)


def test_real_e2e_computed_ratings_view_sums_defensive_points_per_match(
    run_async,
    real_e2e_session_pool,
):
    async def scenario():
        tournament, club = await _seed_tournament_and_club(
            real_e2e_session_pool,
            tournament_name="Суперлига",
            club_name="Арктик",
        )
        conceded_by_match = [1, 1, 0, 1, 2, 0, 2, 2, 2, 1, 1]

        async with real_e2e_session_pool() as session:
            session.add(
                ScrapedPlayerSeasonStats(
                    external_id="lev-titov",
                    season_key="2025/2026",
                    season_label="2025/2026",
                    season_bucket="current",
                    tournament_name=tournament.name,
                    first_name="Лев",
                    last_name="Титов",
                    position=PlayerPosition.DEFENDER.value,
                    club_id=club.id,
                    games_played=len(conceded_by_match),
                    mvp_count=0,
                    goals=0,
                    assists=0,
                    yellow_cards=0,
                    red_cards=0,
                )
            )
            session.add_all(
                [
                    MatchPlayerStats(
                        match_external_id=f"match-{index}",
                        match_url=f"https://olesports.ru/match/match-{index}",
                        tournament_id=tournament.id,
                        club_id=club.id,
                        season_key="2025/2026",
                        season_label="2025/2026",
                        player_external_id="lev-titov",
                        player_name="Лев Титов",
                        team_name="Арктик",
                        opponent_name=f"Соперник {index}",
                        match_date_label=f"2026-07-{index:02d}",
                        is_home=bool(index % 2),
                        in_roster=True,
                        started=index % 3 != 0,
                        mvp=False,
                        team_won=goals_conceded < 2,
                        team_goals=2,
                        opponent_goals=goals_conceded,
                        goals_conceded=goals_conceded,
                    )
                    for index, goals_conceded in enumerate(conceded_by_match, start=1)
                ]
            )
            await session.commit()

            result = await session.execute(
                select(_computed_ratings_view)
                .where(_computed_ratings_view.c.external_id == "lev-titov")
                .where(_computed_ratings_view.c.season_label == "2025/2026")
            )
            row = result.mappings().one()

        assert row["goals_conceded"] == sum(conceded_by_match)
        assert row["defensive_points"] == 62

    run_async(scenario())
