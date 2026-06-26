"""add match player stats

Revision ID: 008
Revises: 007
Create Date: 2026-06-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "match_stats" not in set(inspector.get_table_names()):
        op.create_table(
            "match_stats",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("match_external_id", sa.String(100), nullable=False),
            sa.Column("match_url", sa.String(500), nullable=False),
            sa.Column(
                "tournament_id",
                sa.Integer(),
                sa.ForeignKey("tournaments.id"),
                nullable=False,
            ),
            sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
            sa.Column("player_external_id", sa.String(100), nullable=False),
            sa.Column("player_name", sa.String(200), nullable=False),
            sa.Column("team_name", sa.String(200), nullable=False),
            sa.Column("opponent_name", sa.String(200), nullable=False),
            sa.Column("match_date_label", sa.String(100), nullable=True),
            sa.Column("is_home", sa.Boolean(), nullable=False),
            sa.Column(
                "in_roster",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column(
                "started",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("mvp", sa.Boolean(), server_default=sa.text("false"), nullable=False),
            sa.Column(
                "team_won",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
            sa.Column("team_goals", sa.Integer(), nullable=False),
            sa.Column("opponent_goals", sa.Integer(), nullable=False),
            sa.Column("goals_conceded", sa.Integer(), nullable=False),
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
                "match_external_id",
                "player_external_id",
                name="uq_match_stats_match_player",
            ),
        )

    match_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("match_stats")}
    if "ix_match_stats_match_external_id" not in match_indexes:
        op.create_index(
            "ix_match_stats_match_external_id",
            "match_stats",
            ["match_external_id"],
        )
    if "ix_match_stats_player_external_id" not in match_indexes:
        op.create_index(
            "ix_match_stats_player_external_id",
            "match_stats",
            ["player_external_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_match_stats_player_external_id", table_name="match_stats")
    op.drop_index("ix_match_stats_match_external_id", table_name="match_stats")
    op.drop_table("match_stats")
