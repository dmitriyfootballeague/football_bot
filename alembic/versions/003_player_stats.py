"""add player match statistics columns

Revision ID: 003
Revises: 002
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("players", sa.Column("games_played", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("mvp_count", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("goals", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("assists", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("yellow_cards", sa.Integer(), nullable=True))
    op.add_column("players", sa.Column("red_cards", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "red_cards")
    op.drop_column("players", "yellow_cards")
    op.drop_column("players", "assists")
    op.drop_column("players", "goals")
    op.drop_column("players", "mvp_count")
    op.drop_column("players", "games_played")
