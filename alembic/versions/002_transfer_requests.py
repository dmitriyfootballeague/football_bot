"""add transfer_requests table

Revision ID: 002
Revises: 001
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    transfer_type = sa.Enum(
        "exit", "join", "invite",
        name="transfertype",
    )
    transfer_status = sa.Enum(
        "pending_captain", "pending_player", "pending_captain_confirm",
        "pending_admin", "approved", "rejected",
        name="transferstatus",
    )

    op.create_table(
        "transfer_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("transfer_type", transfer_type, nullable=False),
        sa.Column("status", transfer_status, nullable=False),
        sa.Column("from_club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
        sa.Column("to_club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
        sa.Column("initiated_by", sa.BigInteger(), nullable=False),
        sa.Column("rejected_by", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transfer_requests_player_id", "transfer_requests", ["player_id"])
    op.create_index("ix_transfer_requests_status", "transfer_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_transfer_requests_status", table_name="transfer_requests")
    op.drop_index("ix_transfer_requests_player_id", table_name="transfer_requests")
    op.drop_table("transfer_requests")
    sa.Enum(name="transfertype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transferstatus").drop(op.get_bind(), checkfirst=True)
