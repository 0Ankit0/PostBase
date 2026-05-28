"""merge current heads

Revision ID: 8f1c6d4b2a7e
Revises: 5d7b9c1e2f3a, f4c8e2a1b3d5
Create Date: 2026-05-27 00:00:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "8f1c6d4b2a7e"
down_revision: Union[str, Sequence[str], None] = ("5d7b9c1e2f3a", "f4c8e2a1b3d5")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge schema heads without additional DDL."""


def downgrade() -> None:
    """Restore the previous independent schema heads."""
