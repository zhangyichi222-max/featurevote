"""remove post comments

Revision ID: 202606241100
Revises: 202606221430
Create Date: 2026-06-24 11:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606241100"
down_revision: Union[str, None] = "202606221430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("comments"):
        op.drop_table("comments")


def downgrade() -> None:
    if not _has_table("comments"):
        op.create_table(
            "comments",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("post_id", sa.String(length=32), nullable=False),
            sa.Column("user_id", sa.String(length=32), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("is_approved", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
