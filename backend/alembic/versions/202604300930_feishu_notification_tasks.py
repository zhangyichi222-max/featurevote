"""add feishu notification outbox

Revision ID: 202604300930
Revises: 202604281735
Create Date: 2026-04-30 09:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202604300930"
down_revision: Union[str, None] = "202604281735"
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
    if not _has_column("posts", "hot_at"):
        op.add_column("posts", sa.Column("hot_at", sa.DateTime(), nullable=True))

    if not _has_table("notification_tasks"):
        op.create_table(
            "notification_tasks",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("post_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("recipient_open_id", sa.String(length=255), nullable=True),
            sa.Column("event_type", sa.String(length=32), nullable=False),
            sa.Column("dedupe_key", sa.String(length=120), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("max_attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("sent_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("post_id", "event_type", "dedupe_key", name="uq_notification_tasks_dedupe"),
        )
        op.create_index("ix_notification_tasks_status_next", "notification_tasks", ["status", "next_attempt_at"])


def downgrade() -> None:
    if _has_table("notification_tasks"):
        op.drop_index("ix_notification_tasks_status_next", table_name="notification_tasks")
        op.drop_table("notification_tasks")
    if _has_column("posts", "hot_at"):
        op.drop_column("posts", "hot_at")
