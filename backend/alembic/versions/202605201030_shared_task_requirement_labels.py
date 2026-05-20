"""share labels between tasks and requirements

Revision ID: 202605201030
Revises: 202605091430
Create Date: 2026-05-20 10:30:00
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "202605201030"
down_revision: Union[str, None] = "202605091430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _task_label_links_table(foreign_table: str) -> None:
    op.create_table(
        "task_label_links",
        sa.Column("task_id", sa.String(length=32), nullable=False),
        sa.Column("label_id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["label_id"], [f"{foreign_table}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "label_id"),
        sa.UniqueConstraint("task_id", "label_id", name="uq_task_label_links_task_label"),
    )


def upgrade() -> None:
    if not (_has_table("tags") and _has_table("tasks")):
        return

    bind = op.get_bind()
    old_labels = sa.table(
        "task_labels",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("color", sa.String),
    )
    tags = sa.table(
        "tags",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("color", sa.String),
        sa.column("is_public", sa.Boolean),
    )
    old_links = sa.table(
        "task_label_links",
        sa.column("task_id", sa.String),
        sa.column("label_id", sa.String),
    )

    label_id_map: dict[str, str] = {}
    if _has_table("task_labels"):
        existing_tags = {
            (row["tenant_id"], row["slug"]): row["id"]
            for row in bind.execute(sa.select(tags.c.id, tags.c.tenant_id, tags.c.slug)).mappings()
        }
        for label in bind.execute(sa.select(old_labels)).mappings():
            key = (label["tenant_id"], label["slug"])
            tag_id = existing_tags.get(key)
            if tag_id is None:
                tag_id = uuid4().hex
                bind.execute(
                    tags.insert().values(
                        id=tag_id,
                        tenant_id=label["tenant_id"],
                        name=label["name"],
                        slug=label["slug"],
                        color=label["color"],
                        is_public=True,
                    )
                )
                existing_tags[key] = tag_id
            label_id_map[label["id"]] = tag_id

    rewritten_links: set[tuple[str, str]] = set()
    if _has_table("task_label_links"):
        for link in bind.execute(sa.select(old_links)).mappings():
            tag_id = label_id_map.get(link["label_id"], link["label_id"])
            rewritten_links.add((link["task_id"], tag_id))
        op.drop_table("task_label_links")

    _task_label_links_table("tags")
    if rewritten_links:
        op.bulk_insert(
            old_links,
            [{"task_id": task_id, "label_id": label_id} for task_id, label_id in sorted(rewritten_links)],
        )

    if _has_table("task_labels"):
        op.drop_table("task_labels")


def downgrade() -> None:
    if not (_has_table("tags") and _has_table("tasks")):
        return

    bind = op.get_bind()
    tags = sa.table(
        "tags",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("color", sa.String),
    )
    links = sa.table(
        "task_label_links",
        sa.column("task_id", sa.String),
        sa.column("label_id", sa.String),
    )
    task_labels = sa.table(
        "task_labels",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("color", sa.String),
    )

    existing_links: set[tuple[str, str]] = set()
    if _has_table("task_label_links"):
        existing_links = {
            (row["task_id"], row["label_id"])
            for row in bind.execute(sa.select(links.c.task_id, links.c.label_id)).mappings()
        }
        op.drop_table("task_label_links")

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

    linked_label_ids = {label_id for _, label_id in existing_links}
    if linked_label_ids:
        linked_tags = bind.execute(sa.select(tags).where(tags.c.id.in_(linked_label_ids))).mappings()
        op.bulk_insert(
            task_labels,
            [
                {
                    "id": tag["id"],
                    "tenant_id": tag["tenant_id"],
                    "name": tag["name"],
                    "slug": tag["slug"],
                    "color": tag["color"],
                }
                for tag in linked_tags
            ],
        )

    _task_label_links_table("task_labels")
    if existing_links:
        op.bulk_insert(
            links,
            [{"task_id": task_id, "label_id": label_id} for task_id, label_id in sorted(existing_links)],
        )
