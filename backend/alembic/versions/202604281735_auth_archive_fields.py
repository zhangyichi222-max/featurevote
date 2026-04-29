"""add feishu auth and archive fields

Revision ID: 202604281735
Revises: 202604281730
Create Date: 2026-04-28 17:35:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202604281735"
down_revision: Union[str, None] = "202604281730"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_constraint(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints(table_name) + inspector.get_foreign_keys(table_name)
    return any(constraint.get("name") == constraint_name for constraint in constraints)


def upgrade() -> None:
    if not _has_column("users", "feishu_open_id"):
        op.add_column("users", sa.Column("feishu_open_id", sa.String(length=255), nullable=True))
    if not _has_column("users", "feishu_union_id"):
        op.add_column("users", sa.Column("feishu_union_id", sa.String(length=255), nullable=True))
    if not _has_column("users", "email"):
        op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    if not _has_column("users", "avatar_url"):
        op.add_column("users", sa.Column("avatar_url", sa.String(length=1024), nullable=True))
    if not _has_column("users", "department_ids"):
        op.add_column("users", sa.Column("department_ids", sa.Text(), nullable=True))
        op.execute(sa.text("UPDATE users SET department_ids = '' WHERE department_ids IS NULL"))
        op.alter_column("users", "department_ids", existing_type=sa.Text(), nullable=False)
    if not _has_column("users", "group_ids"):
        op.add_column("users", sa.Column("group_ids", sa.Text(), nullable=True))
        op.execute(sa.text("UPDATE users SET group_ids = '' WHERE group_ids IS NULL"))
        op.alter_column("users", "group_ids", existing_type=sa.Text(), nullable=False)
    if not _has_column("users", "updated_at"):
        op.add_column(
            "users",
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )
    if not _has_constraint("users", "uq_users_tenant_feishu_open"):
        op.create_unique_constraint("uq_users_tenant_feishu_open", "users", ["tenant_id", "feishu_open_id"])

    if not _has_column("posts", "archived_at"):
        op.add_column("posts", sa.Column("archived_at", sa.DateTime(), nullable=True))
    if not _has_column("posts", "archived_by_user_id"):
        op.add_column("posts", sa.Column("archived_by_user_id", sa.String(length=32), nullable=True))
    if not _has_constraint("posts", "fk_posts_archived_by_user"):
        op.create_foreign_key("fk_posts_archived_by_user", "posts", "users", ["archived_by_user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_posts_archived_by_user", "posts", type_="foreignkey")
    op.drop_column("posts", "archived_by_user_id")
    op.drop_column("posts", "archived_at")

    op.drop_constraint("uq_users_tenant_feishu_open", "users", type_="unique")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "group_ids")
    op.drop_column("users", "department_ids")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "email")
    op.drop_column("users", "feishu_union_id")
    op.drop_column("users", "feishu_open_id")
