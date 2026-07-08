"""drop computed rating columns from scraped player snapshots

Revision ID: 014
Revises: 013
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "scraped_player_stats"
RATING_COLUMNS = (
    "current_rating",
    "division_rank",
    "division_total",
    "avg_points_per_game",
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns(TABLE_NAME)
    }

    for column_name in RATING_COLUMNS:
        if column_name in existing_columns:
            op.drop_column(TABLE_NAME, column_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {
        column["name"] for column in inspector.get_columns(TABLE_NAME)
    }

    if "current_rating" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("current_rating", sa.Float(), nullable=True))
    if "division_rank" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("division_rank", sa.Integer(), nullable=True))
    if "division_total" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("division_total", sa.Integer(), nullable=True))
    if "avg_points_per_game" not in existing_columns:
        op.add_column(TABLE_NAME, sa.Column("avg_points_per_game", sa.Float(), nullable=True))
