"""remove hot vote notifications

Revision ID: 202606241130
Revises: 202606241100
Create Date: 2026-06-24 11:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606241130"
down_revision: Union[str, None] = "202606241100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("notification_tasks"):
        op.execute(sa.text("DELETE FROM notification_tasks WHERE event_type = 'hot'"))
    if _has_column("posts", "hot_at"):
        op.drop_column("posts", "hot_at")


def downgrade() -> None:
    if _has_table("posts") and not _has_column("posts", "hot_at"):
        op.add_column("posts", sa.Column("hot_at", sa.DateTime(), nullable=True))
