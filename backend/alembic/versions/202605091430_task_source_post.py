"""link tasks to source posts

Revision ID: 202605091430
Revises: 202605091120
Create Date: 2026-05-09 14:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202605091430"
down_revision: Union[str, None] = "202605091120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("tasks") and not _has_column("tasks", "source_post_id"):
        op.add_column("tasks", sa.Column("source_post_id", sa.String(length=32), nullable=True))
        op.create_foreign_key(
            "fk_tasks_source_post_id_posts",
            "tasks",
            "posts",
            ["source_post_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_unique_constraint("uq_tasks_tenant_source_post", "tasks", ["tenant_id", "source_post_id"])


def downgrade() -> None:
    if _has_table("tasks") and _has_column("tasks", "source_post_id"):
        op.drop_constraint("uq_tasks_tenant_source_post", "tasks", type_="unique")
        op.drop_constraint("fk_tasks_source_post_id_posts", "tasks", type_="foreignkey")
        op.drop_column("tasks", "source_post_id")
