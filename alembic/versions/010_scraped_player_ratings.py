"""add computed rating fields to scraped_player_stats

Revision ID: 010
Revises: 009
Create Date: 2026-06-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("scraped_player_stats")
    }
    if "current_rating" not in existing_columns:
        op.add_column(
            "scraped_player_stats",
            sa.Column("current_rating", sa.Float(), nullable=True),
        )
    if "division_rank" not in existing_columns:
        op.add_column(
            "scraped_player_stats",
            sa.Column("division_rank", sa.Integer(), nullable=True),
        )
    if "division_total" not in existing_columns:
        op.add_column(
            "scraped_player_stats",
            sa.Column("division_total", sa.Integer(), nullable=True),
        )
    if "avg_points_per_game" not in existing_columns:
        op.add_column(
            "scraped_player_stats",
            sa.Column("avg_points_per_game", sa.Float(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("scraped_player_stats", "avg_points_per_game")
    op.drop_column("scraped_player_stats", "division_total")
    op.drop_column("scraped_player_stats", "division_rank")
    op.drop_column("scraped_player_stats", "current_rating")
