"""add secret versioning and rotation fields

Revision ID: ab12cd34ef56
Revises: d9b7e3a1c2f4
Create Date: 2026-04-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ab12cd34ef56"
down_revision = "d9b7e3a1c2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postbase_secret_ref", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "postbase_secret_ref",
        sa.Column("is_active_version", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("postbase_secret_ref", sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("postbase_secret_ref", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint("uq_postbase_secret_ref_env_name", "postbase_secret_ref", type_="unique")
    op.create_unique_constraint(
        "uq_postbase_secret_ref_env_name_version",
        "postbase_secret_ref",
        ["environment_id", "name", "version"],
    )
    op.create_index(
        "uq_postbase_secret_ref_active_version_per_name",
        "postbase_secret_ref",
        ["environment_id", "name"],
        unique=True,
        sqlite_where=sa.text("is_active_version = 1"),
        postgresql_where=sa.text("is_active_version = true"),
    )

    op.execute(
        """
        UPDATE postbase_secret_ref
        SET version = 1,
            is_active_version = CASE WHEN status = 'active' THEN TRUE ELSE FALSE END,
            rotated_at = CASE WHEN status = 'active' THEN updated_at ELSE NULL END
        """
    )

    op.alter_column("postbase_secret_ref", "version", server_default=None)
    op.alter_column("postbase_secret_ref", "is_active_version", server_default=None)


def downgrade() -> None:
    op.drop_index("uq_postbase_secret_ref_active_version_per_name", table_name="postbase_secret_ref")
    op.drop_constraint("uq_postbase_secret_ref_env_name_version", "postbase_secret_ref", type_="unique")
    op.create_unique_constraint("uq_postbase_secret_ref_env_name", "postbase_secret_ref", ["environment_id", "name"])

    op.drop_column("postbase_secret_ref", "expires_at")
    op.drop_column("postbase_secret_ref", "rotated_at")
    op.drop_column("postbase_secret_ref", "is_active_version")
    op.drop_column("postbase_secret_ref", "version")
