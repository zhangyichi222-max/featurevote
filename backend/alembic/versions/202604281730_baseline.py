"""baseline existing product core schema

Revision ID: 202604281730
Revises: None
Create Date: 2026-04-28 17:30:00
"""
from typing import Sequence, Union

revision: str = "202604281730"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
