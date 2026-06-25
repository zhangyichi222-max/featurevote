"""add feishu context and embedding index metadata

Revision ID: 202606251000
Revises: 202606241200
Create Date: 2026-06-25 10:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "202606251000"
down_revision: Union[str, None] = "202606241200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _columns("feishu_imported_messages")
    additions = [
        ("chat_name", sa.String(length=255), True),
        ("root_id", sa.String(length=255), True),
        ("parent_id", sa.String(length=255), True),
        ("sent_at", sa.DateTime(), True),
        ("is_direct_source", sa.Boolean(), False),
    ]
    for name, column_type, nullable in additions:
        if name not in columns:
            op.add_column(
                "feishu_imported_messages",
                sa.Column(name, column_type, nullable=nullable, server_default=sa.false() if name == "is_direct_source" else None),
            )
    if "is_direct_source" not in columns:
        op.execute(
            sa.text(
                "UPDATE feishu_imported_messages "
                "SET is_direct_source = true WHERE post_id IS NOT NULL"
            )
        )

    inspector = sa.inspect(op.get_bind())
    if "post_embedding_indexes" not in inspector.get_table_names():
        op.create_table(
            "post_embedding_indexes",
            sa.Column("id", sa.String(length=32), nullable=False),
            sa.Column("tenant_id", sa.String(length=32), nullable=False),
            sa.Column("post_id", sa.String(length=32), nullable=False),
            sa.Column("model", sa.String(length=120), nullable=False),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("indexed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["post_id"], ["posts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("post_id", name="uq_post_embedding_indexes_post"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "post_embedding_indexes" in inspector.get_table_names():
        op.drop_table("post_embedding_indexes")
    columns = _columns("feishu_imported_messages")
    for name in ["is_direct_source", "sent_at", "parent_id", "root_id", "chat_name"]:
        if name in columns:
            op.drop_column("feishu_imported_messages", name)
