"""enforce active binding uniqueness

Revision ID: d9b7e3a1c2f4
Revises: c4e8a9f1d2b3
Create Date: 2026-04-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d9b7e3a1c2f4"
down_revision = "c4e8a9f1d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_postbase_capability_binding_active_per_capability_env",
        "postbase_capability_binding",
        ["environment_id", "capability_type_id"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_postbase_capability_binding_active_per_capability_env",
        table_name="postbase_capability_binding",
    )
