"""add binding transition audit fields

Revision ID: c4e8a9f1d2b3
Revises: f2d4c6b8e9a1
Create Date: 2026-04-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4e8a9f1d2b3"
down_revision = "f2d4c6b8e9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "postbase_capability_binding",
        sa.Column("last_transition_actor_user_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "postbase_capability_binding",
        sa.Column("last_transition_reason", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "postbase_capability_binding",
        sa.Column("last_transition_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_postbase_capability_binding_last_transition_actor_user_id",
        "postbase_capability_binding",
        ["last_transition_actor_user_id"],
        unique=False,
    )
    op.alter_column(
        "postbase_capability_binding",
        "last_transition_reason",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_postbase_capability_binding_last_transition_actor_user_id",
        table_name="postbase_capability_binding",
    )
    op.drop_column("postbase_capability_binding", "last_transition_at")
    op.drop_column("postbase_capability_binding", "last_transition_reason")
    op.drop_column("postbase_capability_binding", "last_transition_actor_user_id")
