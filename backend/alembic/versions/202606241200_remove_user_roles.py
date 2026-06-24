"""remove user roles

Revision ID: 202606241200
Revises: 202606241130
Create Date: 2026-06-24 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606241200"
down_revision: Union[str, None] = "202606241130"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("users", "role"):
        op.drop_column("users", "role")


def downgrade() -> None:
    if not _has_column("users", "role"):
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=32), nullable=False, server_default="visitor"),
        )
