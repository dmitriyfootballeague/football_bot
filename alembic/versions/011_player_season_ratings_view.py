"""add season-scoped scraped player stats and computed ratings view

Revision ID: 011
Revises: 010
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
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
                ) AS current_rating
            FROM scraped_player_season_stats s
            LEFT JOIN match_agg
                ON match_agg.season_stat_id = s.id
        ),
        ranked AS (
            SELECT
                scored.*,
                ROUND(
                    CASE
                        WHEN scored.games_played > 0
                            THEN (scored.current_rating / scored.games_played)::numeric
                        ELSE 0
                    END,
                    2
                ) AS avg_points_per_game,
                ROW_NUMBER() OVER (
                    PARTITION BY scored.season_key, scored.division_key
                    ORDER BY scored.current_rating DESC, scored.external_id
                ) AS division_rank,
                COUNT(*) OVER (
                    PARTITION BY scored.season_key, scored.division_key
                ) AS division_total,
                CASE
                    WHEN scored.position IS NULL THEN NULL
                    ELSE ROW_NUMBER() OVER (
                        PARTITION BY scored.season_key, scored.position
                        ORDER BY scored.current_rating DESC, scored.external_id
                    )
                END AS position_rank,
                CASE
                    WHEN scored.position IS NULL THEN NULL
                    ELSE COUNT(*) OVER (
                        PARTITION BY scored.season_key, scored.position
                    )
                END AS position_total
            FROM scored
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
            wins,
            starts,
            goals_conceded,
            defensive_points,
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
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "scraped_player_season_stats" not in set(inspector.get_table_names()):
        op.create_table(
            "scraped_player_season_stats",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("external_id", sa.String(100), nullable=False),
            sa.Column("season_key", sa.String(100), nullable=False),
            sa.Column("season_label", sa.String(200), nullable=False),
            sa.Column("season_bucket", sa.String(20), nullable=False),
            sa.Column("tournament_name", sa.String(200), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=False),
            sa.Column("position", sa.String(100), nullable=True),
            sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
            sa.Column("games_played", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("mvp_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("goals", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("assists", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("yellow_cards", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("red_cards", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("scraped_rating", sa.Float(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "external_id",
                "season_label",
                name="uq_scraped_player_season_stats_external_id_season_label",
            ),
        )

    season_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("scraped_player_season_stats")
    }
    if "ix_scraped_player_season_stats_external_id" not in season_indexes:
        op.create_index(
            "ix_scraped_player_season_stats_external_id",
            "scraped_player_season_stats",
            ["external_id"],
        )
    if "ix_scraped_player_season_stats_season_key" not in season_indexes:
        op.create_index(
            "ix_scraped_player_season_stats_season_key",
            "scraped_player_season_stats",
            ["season_key"],
        )
    if "ix_scraped_player_season_stats_season_label" not in season_indexes:
        op.create_index(
            "ix_scraped_player_season_stats_season_label",
            "scraped_player_season_stats",
            ["season_label"],
        )
    if "ix_scraped_player_season_stats_club_id" not in season_indexes:
        op.create_index(
            "ix_scraped_player_season_stats_club_id",
            "scraped_player_season_stats",
            ["club_id"],
        )

    match_columns = {column["name"] for column in inspector.get_columns("match_stats")}
    if "season_key" not in match_columns:
        op.add_column("match_stats", sa.Column("season_key", sa.String(100), nullable=True))
    if "season_label" not in match_columns:
        op.add_column("match_stats", sa.Column("season_label", sa.String(200), nullable=True))

    match_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("match_stats")}
    if "ix_match_stats_player_external_id_season_label" not in match_indexes:
        op.create_index(
            "ix_match_stats_player_external_id_season_label",
            "match_stats",
            ["player_external_id", "season_label"],
        )

    _create_or_replace_view()


def downgrade() -> None:
    op.execute(f"DROP VIEW IF EXISTS {VIEW_NAME}")
    op.drop_index(
        "ix_match_stats_player_external_id_season_label",
        table_name="match_stats",
    )
    op.drop_column("match_stats", "season_label")
    op.drop_column("match_stats", "season_key")
    op.drop_index(
        "ix_scraped_player_season_stats_club_id",
        table_name="scraped_player_season_stats",
    )
    op.drop_index(
        "ix_scraped_player_season_stats_season_label",
        table_name="scraped_player_season_stats",
    )
    op.drop_index(
        "ix_scraped_player_season_stats_season_key",
        table_name="scraped_player_season_stats",
    )
    op.drop_index(
        "ix_scraped_player_season_stats_external_id",
        table_name="scraped_player_season_stats",
    )
    op.drop_table("scraped_player_season_stats")
