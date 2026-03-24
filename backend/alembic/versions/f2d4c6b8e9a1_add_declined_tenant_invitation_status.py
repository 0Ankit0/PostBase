"""add_declined_tenant_invitation_status

Revision ID: f2d4c6b8e9a1
Revises: b7c1d2e3f4a5
Create Date: 2026-03-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2d4c6b8e9a1'
down_revision: Union[str, Sequence[str], None] = 'b7c1d2e3f4a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_INVITATION_STATUS = sa.Enum(
    'PENDING',
    'ACCEPTED',
    'EXPIRED',
    'REVOKED',
    name='invitationstatus',
)

_NEW_INVITATION_STATUS = sa.Enum(
    'PENDING',
    'ACCEPTED',
    'DECLINED',
    'EXPIRED',
    'REVOKED',
    name='invitationstatus',
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        op.execute("ALTER TYPE invitationstatus ADD VALUE IF NOT EXISTS 'DECLINED'")
        return

    with op.batch_alter_table('tenantinvitation', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=_OLD_INVITATION_STATUS,
            type_=_NEW_INVITATION_STATUS,
            existing_nullable=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        # PostgreSQL enums cannot remove values in place; keep schema compatible.
        return

    op.execute(
        sa.text(
            "UPDATE tenantinvitation SET status = 'REVOKED' WHERE status = 'DECLINED'"
        )
    )
    with op.batch_alter_table('tenantinvitation', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=_NEW_INVITATION_STATUS,
            type_=_OLD_INVITATION_STATUS,
            existing_nullable=False,
        )
