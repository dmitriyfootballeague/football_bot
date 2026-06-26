"""add scraped_player_stats table and player.external_id

Revision ID: 004
Revises: 003
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    player_columns = {column["name"] for column in inspector.get_columns("players")}
    if "external_id" not in player_columns:
        op.add_column("players", sa.Column("external_id", sa.String(100), nullable=True))

    player_indexes = {index["name"] for index in inspector.get_indexes("players")}
    if "ix_players_external_id" not in player_indexes:
        op.create_index("ix_players_external_id", "players", ["external_id"], unique=True)

    if "scraped_player_stats" not in set(inspector.get_table_names()):
        op.create_table(
            "scraped_player_stats",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("external_id", sa.String(100), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=False),
            sa.Column("last_name", sa.String(100), nullable=False),
            sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
            sa.Column("games_played", sa.Integer(), server_default="0", nullable=False),
            sa.Column("mvp_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("goals", sa.Integer(), server_default="0", nullable=False),
            sa.Column("assists", sa.Integer(), server_default="0", nullable=False),
            sa.Column("yellow_cards", sa.Integer(), server_default="0", nullable=False),
            sa.Column("red_cards", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    scraped_indexes = {
        index["name"] for index in sa.inspect(bind).get_indexes("scraped_player_stats")
    }
    if "ix_scraped_player_stats_external_id" not in scraped_indexes:
        op.create_index("ix_scraped_player_stats_external_id", "scraped_player_stats", ["external_id"], unique=True)
    if "ix_scraped_player_stats_club_id" not in scraped_indexes:
        op.create_index("ix_scraped_player_stats_club_id", "scraped_player_stats", ["club_id"])


def downgrade() -> None:
    op.drop_index("ix_scraped_player_stats_club_id", table_name="scraped_player_stats")
    op.drop_index("ix_scraped_player_stats_external_id", table_name="scraped_player_stats")
    op.drop_table("scraped_player_stats")
    op.drop_index("ix_players_external_id", table_name="players")
    op.drop_column("players", "external_id")
