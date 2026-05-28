"""add postgres advanced table features

Revision ID: f4c8e2a1b3d5
Revises: ab12cd34ef56, e3a4f6b7c8d9
Create Date: 2026-05-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4c8e2a1b3d5"
down_revision = ("ab12cd34ef56", "e3a4f6b7c8d9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("postbase_table_definition"):
        return

    op.add_column(
        "postbase_table_definition",
        sa.Column(
            "advanced_features_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("postbase_table_definition", "advanced_features_json", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("postbase_table_definition"):
        return

    op.drop_column("postbase_table_definition", "advanced_features_json")
