"""initial

Revision ID: 001
Revises:
Create Date: 2026-02-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "divisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "clubs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("division_id", sa.Integer(), sa.ForeignKey("divisions.id"), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    player_role = sa.Enum("player", "captain", "free_agent", name="playerrole")
    player_position = sa.Enum("goalkeeper", "defender", "midfielder", "forward", name="playerposition")
    registration_status = sa.Enum("pending", "approved", "rejected", name="registrationstatus")

    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(100), nullable=True),
        # Registration fields
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("position", player_position, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("photo_file_id", sa.String(200), nullable=False),
        # Status fields
        sa.Column("role", player_role, nullable=False),
        sa.Column("registration_status", registration_status, server_default="pending"),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
        # Current season rating
        sa.Column("current_rating", sa.Float(), nullable=True),
        sa.Column("division_rank", sa.Integer(), nullable=True),
        sa.Column("division_total", sa.Integer(), nullable=True),
        sa.Column("position_rank", sa.Integer(), nullable=True),
        sa.Column("position_total", sa.Integer(), nullable=True),
        sa.Column("avg_points_per_game", sa.Float(), nullable=True),
        sa.Column("rating_updated_at", sa.DateTime(timezone=True), nullable=True),
        # Previous season rating
        sa.Column("prev_season_rating", sa.Float(), nullable=True),
        sa.Column("prev_division_rank", sa.Integer(), nullable=True),
        sa.Column("prev_division_total", sa.Integer(), nullable=True),
        sa.Column("prev_position_rank", sa.Integer(), nullable=True),
        sa.Column("prev_position_total", sa.Integer(), nullable=True),
        sa.Column("prev_avg_points", sa.Float(), nullable=True),
        # Misc
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_players_telegram_id", "players", ["telegram_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_players_telegram_id", table_name="players")
    op.drop_table("players")
    op.drop_table("clubs")
    op.drop_table("divisions")
    sa.Enum(name="playerrole").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="playerposition").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="registrationstatus").drop(op.get_bind(), checkfirst=True)
