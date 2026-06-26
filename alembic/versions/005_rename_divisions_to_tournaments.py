"""rename divisions table to tournaments

Revision ID: 005
Revises: 004
Create Date: 2026-02-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "divisions" in tables and "tournaments" not in tables:
        op.rename_table("divisions", "tournaments")

    club_columns = {
        column["name"] for column in sa.inspect(bind).get_columns("clubs")
    }
    if "division_id" in club_columns and "tournament_id" not in club_columns:
        op.alter_column("clubs", "division_id", new_column_name="tournament_id")


def downgrade() -> None:
    op.alter_column("clubs", "tournament_id", new_column_name="division_id")
    op.rename_table("tournaments", "divisions")
