"""add task management

Revision ID: 202605091120
Revises: 202604300930
Create Date: 2026-05-09 11:20:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202605091120"
down_revision: Union[str, None] = "202604300930"
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
    if not _has_table("tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("description_markdown", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("assignee_user_id", sa.String(length=32), nullable=True),
            sa.Column("created_by_user_id", sa.String(length=32), nullable=False),
            sa.Column("updated_by_user_id", sa.String(length=32), nullable=True),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["assignee_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "number", name="uq_tasks_tenant_number"),
        )

    if not _has_table("task_labels"):
        op.create_table(
            "task_labels",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("slug", sa.String(length=80), nullable=False),
            sa.Column("color", sa.String(length=24), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id", "slug", name="uq_task_labels_tenant_slug"),
        )

    if not _has_table("task_label_links"):
        op.create_table(
            "task_label_links",
            sa.Column("task_id", sa.String(length=32), nullable=False),
            sa.Column("label_id", sa.String(length=32), nullable=False),
            sa.ForeignKeyConstraint(["label_id"], ["task_labels.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("task_id", "label_id"),
            sa.UniqueConstraint("task_id", "label_id", name="uq_task_label_links_task_label"),
        )

    if _has_table("notification_tasks") and not _has_column("notification_tasks", "task_id"):
        op.add_column("notification_tasks", sa.Column("task_id", sa.String(length=32), nullable=True))
        op.create_foreign_key(
            "fk_notification_tasks_task_id_tasks",
            "notification_tasks",
            "tasks",
            ["task_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_unique_constraint(
            "uq_notification_tasks_task_dedupe",
            "notification_tasks",
            ["task_id", "event_type", "dedupe_key"],
        )
        op.alter_column("notification_tasks", "post_id", existing_type=sa.String(length=32), nullable=True)


def downgrade() -> None:
    if _has_table("notification_tasks") and _has_column("notification_tasks", "task_id"):
        op.drop_constraint("uq_notification_tasks_task_dedupe", "notification_tasks", type_="unique")
        op.drop_constraint("fk_notification_tasks_task_id_tasks", "notification_tasks", type_="foreignkey")
        op.drop_column("notification_tasks", "task_id")
        op.alter_column("notification_tasks", "post_id", existing_type=sa.String(length=32), nullable=False)

    if _has_table("task_label_links"):
        op.drop_table("task_label_links")
    if _has_table("task_labels"):
        op.drop_table("task_labels")
    if _has_table("tasks"):
        op.drop_table("tasks")
