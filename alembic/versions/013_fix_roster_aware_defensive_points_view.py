"""make defensive rating aggregates roster-aware

Revision ID: 013
Revises: 012
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEW_NAME = "computed_scraped_player_ratings"


def _create_or_replace_view() -> None:
    op.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
    op.execute(
        f"""
        CREATE VIEW {VIEW_NAME} AS
        WITH match_agg AS (
            SELECT
                s.id AS season_stat_id,
                COUNT(*) FILTER (WHERE m.in_roster AND m.team_won) AS wins,
                COUNT(*) FILTER (WHERE m.in_roster AND m.started) AS starts,
                COALESCE(SUM(CASE WHEN m.in_roster THEN m.goals_conceded ELSE 0 END), 0) AS goals_conceded,
                COALESCE(
                    SUM(
                        CASE
                            WHEN m.in_roster AND s.position = 'attacking_midfielder' THEN GREATEST(4 - m.goals_conceded, 0)
                            WHEN m.in_roster AND s.position = 'defensive_midfielder' THEN GREATEST(5 - m.goals_conceded, 0)
                            WHEN m.in_roster AND s.position = 'defender' THEN GREATEST(8 - (m.goals_conceded * 2), 0)
                            WHEN m.in_roster AND s.position = 'goalkeeper' THEN GREATEST(8 - (m.goals_conceded * 2), 0)
                            ELSE 0
                        END
                    ),
                    0
                ) AS defensive_points
            FROM scraped_player_season_stats s
            LEFT JOIN match_stats m
                ON m.player_external_id = s.external_id
                AND m.season_label = s.season_label
            GROUP BY s.id
        ),
        scored AS (
            SELECT
                s.id,
                s.external_id,
                s.season_key,
                s.season_label,
                s.season_bucket,
                s.tournament_name,
                COALESCE(
                    NULLIF(TRIM(split_part(s.season_label, '(', 1)), ''),
                    NULLIF(TRIM(split_part(s.tournament_name, '—', 2)), ''),
                    NULLIF(TRIM(split_part(s.tournament_name, ' - ', 2)), ''),
                    s.season_label
                ) AS division_key,
                s.first_name,
                s.last_name,
                s.position,
                s.club_id,
                s.games_played,
                s.mvp_count,
                s.goals,
                s.assists,
                s.yellow_cards,
                s.red_cards,
                s.scraped_rating,
                s.rating_override,
                s.rating_override_updated_at,
                COALESCE(match_agg.wins, 0) AS wins,
                COALESCE(match_agg.starts, 0) AS starts,
                COALESCE(match_agg.goals_conceded, 0) AS goals_conceded,
                COALESCE(match_agg.defensive_points, 0) AS defensive_points,
                ROUND(
                    (
                    CASE
                        WHEN s.games_played <= 0 THEN 0
                        WHEN s.position = 'forward' THEN
                            s.goals * 3
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                        WHEN s.position = 'attacking_midfielder' THEN
                            s.goals * 2
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'defensive_midfielder' THEN
                            s.goals * 2
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'defender' THEN
                            s.goals
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'goalkeeper' THEN
                            s.assists * 3
                            + COALESCE(match_agg.wins, 0) * 2
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        ELSE s.goals * 3 + s.assists + s.mvp_count * 2
                    END
                    )::numeric,
                    2
                ) AS computed_rating
            FROM scraped_player_season_stats s
            LEFT JOIN match_agg
                ON match_agg.season_stat_id = s.id
        ),
        effective AS (
            SELECT
                scored.*,
                COALESCE(scored.rating_override, scored.computed_rating) AS current_rating
            FROM scored
        ),
        ranked AS (
            SELECT
                effective.*,
                ROUND(
                    CASE
                        WHEN effective.games_played > 0
                            THEN (effective.current_rating / effective.games_played)::numeric
                        ELSE 0
                    END,
                    2
                ) AS avg_points_per_game,
                ROW_NUMBER() OVER (
                    PARTITION BY effective.season_key, effective.division_key
                    ORDER BY effective.current_rating DESC, effective.external_id
                ) AS division_rank,
                COUNT(*) OVER (
                    PARTITION BY effective.season_key, effective.division_key
                ) AS division_total,
                CASE
                    WHEN effective.position IS NULL THEN NULL
                    ELSE ROW_NUMBER() OVER (
                        PARTITION BY effective.season_key, effective.position
                        ORDER BY effective.current_rating DESC, effective.external_id
                    )
                END AS position_rank,
                CASE
                    WHEN effective.position IS NULL THEN NULL
                    ELSE COUNT(*) OVER (
                        PARTITION BY effective.season_key, effective.position
                    )
                END AS position_total
            FROM effective
        )
        SELECT
            id,
            external_id,
            season_key,
            season_label,
            season_bucket,
            tournament_name,
            division_key,
            first_name,
            last_name,
            position,
            club_id,
            games_played,
            mvp_count,
            goals,
            assists,
            yellow_cards,
            red_cards,
            scraped_rating,
            rating_override,
            rating_override_updated_at,
            wins,
            starts,
            goals_conceded,
            defensive_points,
            computed_rating,
            current_rating,
            division_rank,
            division_total,
            position_rank,
            position_total,
            avg_points_per_game
        FROM ranked
        """
    )


def _create_or_replace_pre_fix_view() -> None:
    op.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
    op.execute(
        f"""
        CREATE VIEW {VIEW_NAME} AS
        WITH match_agg AS (
            SELECT
                s.id AS season_stat_id,
                COUNT(*) FILTER (WHERE m.team_won) AS wins,
                COUNT(*) FILTER (WHERE m.started) AS starts,
                COALESCE(SUM(m.goals_conceded), 0) AS goals_conceded,
                COALESCE(
                    SUM(
                        CASE
                            WHEN s.position = 'attacking_midfielder' THEN GREATEST(4 - m.goals_conceded, 0)
                            WHEN s.position = 'defensive_midfielder' THEN GREATEST(5 - m.goals_conceded, 0)
                            WHEN s.position = 'defender' THEN GREATEST(8 - (m.goals_conceded * 2), 0)
                            WHEN s.position = 'goalkeeper' THEN GREATEST(8 - (m.goals_conceded * 2), 0)
                            ELSE 0
                        END
                    ),
                    0
                ) AS defensive_points
            FROM scraped_player_season_stats s
            LEFT JOIN match_stats m
                ON m.player_external_id = s.external_id
                AND m.season_label = s.season_label
            GROUP BY s.id
        ),
        scored AS (
            SELECT
                s.id,
                s.external_id,
                s.season_key,
                s.season_label,
                s.season_bucket,
                s.tournament_name,
                COALESCE(
                    NULLIF(TRIM(split_part(s.season_label, '(', 1)), ''),
                    NULLIF(TRIM(split_part(s.tournament_name, '—', 2)), ''),
                    NULLIF(TRIM(split_part(s.tournament_name, ' - ', 2)), ''),
                    s.season_label
                ) AS division_key,
                s.first_name,
                s.last_name,
                s.position,
                s.club_id,
                s.games_played,
                s.mvp_count,
                s.goals,
                s.assists,
                s.yellow_cards,
                s.red_cards,
                s.scraped_rating,
                s.rating_override,
                s.rating_override_updated_at,
                COALESCE(match_agg.wins, 0) AS wins,
                COALESCE(match_agg.starts, 0) AS starts,
                COALESCE(match_agg.goals_conceded, 0) AS goals_conceded,
                COALESCE(match_agg.defensive_points, 0) AS defensive_points,
                ROUND(
                    (
                    CASE
                        WHEN s.games_played <= 0 THEN 0
                        WHEN s.position = 'forward' THEN
                            s.goals * 3
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                        WHEN s.position = 'attacking_midfielder' THEN
                            s.goals * 2
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'defensive_midfielder' THEN
                            s.goals * 2
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'defender' THEN
                            s.goals
                            + s.assists * 3
                            + COALESCE(match_agg.wins, 0)
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        WHEN s.position = 'goalkeeper' THEN
                            s.assists * 3
                            + COALESCE(match_agg.wins, 0) * 2
                            + COALESCE(match_agg.starts, 0)
                            + s.mvp_count
                            + COALESCE(match_agg.defensive_points, 0)
                        ELSE s.goals * 3 + s.assists + s.mvp_count * 2
                    END
                    )::numeric,
                    2
                ) AS computed_rating
            FROM scraped_player_season_stats s
            LEFT JOIN match_agg
                ON match_agg.season_stat_id = s.id
        ),
        effective AS (
            SELECT
                scored.*,
                COALESCE(scored.rating_override, scored.computed_rating) AS current_rating
            FROM scored
        ),
        ranked AS (
            SELECT
                effective.*,
                ROUND(
                    CASE
                        WHEN effective.games_played > 0
                            THEN (effective.current_rating / effective.games_played)::numeric
                        ELSE 0
                    END,
                    2
                ) AS avg_points_per_game,
                ROW_NUMBER() OVER (
                    PARTITION BY effective.season_key, effective.division_key
                    ORDER BY effective.current_rating DESC, effective.external_id
                ) AS division_rank,
                COUNT(*) OVER (
                    PARTITION BY effective.season_key, effective.division_key
                ) AS division_total,
                CASE
                    WHEN effective.position IS NULL THEN NULL
                    ELSE ROW_NUMBER() OVER (
                        PARTITION BY effective.season_key, effective.position
                        ORDER BY effective.current_rating DESC, effective.external_id
                    )
                END AS position_rank,
                CASE
                    WHEN effective.position IS NULL THEN NULL
                    ELSE COUNT(*) OVER (
                        PARTITION BY effective.season_key, effective.position
                    )
                END AS position_total
            FROM effective
        )
        SELECT
            id,
            external_id,
            season_key,
            season_label,
            season_bucket,
            tournament_name,
            division_key,
            first_name,
            last_name,
            position,
            club_id,
            games_played,
            mvp_count,
            goals,
            assists,
            yellow_cards,
            red_cards,
            scraped_rating,
            rating_override,
            rating_override_updated_at,
            wins,
            starts,
            goals_conceded,
            defensive_points,
            computed_rating,
            current_rating,
            division_rank,
            division_total,
            position_rank,
            position_total,
            avg_points_per_game
        FROM ranked
        """
    )


def upgrade() -> None:
    _create_or_replace_view()


def downgrade() -> None:
    _create_or_replace_pre_fix_view()
