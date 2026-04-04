"""rename divisions table to tournaments

Revision ID: 005
Revises: 004
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("divisions", "tournaments")
    op.alter_column("clubs", "division_id", new_column_name="tournament_id")


def downgrade() -> None:
    op.alter_column("clubs", "tournament_id", new_column_name="division_id")
    op.rename_table("tournaments", "divisions")
