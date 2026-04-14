"""add_tenant_invitation_decided_at

Revision ID: 5d7b9c1e2f3a
Revises: f2d4c6b8e9a1
Create Date: 2026-04-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5d7b9c1e2f3a"
down_revision: Union[str, Sequence[str], None] = "f2d4c6b8e9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("tenantinvitation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("decided_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("tenantinvitation", schema=None) as batch_op:
        batch_op.drop_column("decided_at")
