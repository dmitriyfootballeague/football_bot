"""add transfer_requests table

Revision ID: 002
Revises: 001
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if bind.dialect.name == "postgresql":
        enum_type = postgresql.ENUM
        enum_kwargs = {"create_type": False}
    else:
        enum_type = sa.Enum
        enum_kwargs = {}

    transfer_type = enum_type(
        "exit", "join", "invite",
        name="transfertype",
        **enum_kwargs,
    )
    transfer_status = enum_type(
        "pending_captain", "pending_player", "pending_captain_confirm",
        "pending_admin", "approved", "rejected",
        name="transferstatus",
        **enum_kwargs,
    )
    if bind.dialect.name == "postgresql":
        transfer_type.create(bind, checkfirst=True)
        transfer_status.create(bind, checkfirst=True)

    if "transfer_requests" not in tables:
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

    transfer_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("transfer_requests")}
    if "ix_transfer_requests_player_id" not in transfer_indexes:
        op.create_index("ix_transfer_requests_player_id", "transfer_requests", ["player_id"])
    if "ix_transfer_requests_status" not in transfer_indexes:
        op.create_index("ix_transfer_requests_status", "transfer_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_transfer_requests_status", table_name="transfer_requests")
    op.drop_index("ix_transfer_requests_player_id", table_name="transfer_requests")
    op.drop_table("transfer_requests")
    sa.Enum(name="transfertype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transferstatus").drop(op.get_bind(), checkfirst=True)
