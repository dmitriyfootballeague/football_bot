"""add kick transfer enum value

Revision ID: 009
Revises: 008
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE transfertype ADD VALUE IF NOT EXISTS 'kick'")


def downgrade() -> None:
    # PostgreSQL enums cannot drop a single value cheaply; keep downgrade as no-op.
    pass
