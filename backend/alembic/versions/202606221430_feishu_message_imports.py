"""add feishu message import log

Revision ID: 202606221430
Revises: 202605201030
Create Date: 2026-06-22 14:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "202606221430"
down_revision: Union[str, None] = "202605201030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _has_table("feishu_imported_messages"):
        return
    op.create_table(
        "feishu_imported_messages",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("message_id", sa.String(length=255), nullable=False),
        sa.Column("chat_id", sa.String(length=255), nullable=False),
        sa.Column("sender_open_id", sa.String(length=255), nullable=True),
        sa.Column("sender_name", sa.String(length=255), nullable=True),
        sa.Column("post_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_feishu_imported_messages_message"),
    )


def downgrade() -> None:
    if _has_table("feishu_imported_messages"):
        op.drop_table("feishu_imported_messages")
