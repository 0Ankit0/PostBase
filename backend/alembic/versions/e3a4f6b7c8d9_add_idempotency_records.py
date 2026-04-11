"""add idempotency records

Revision ID: e3a4f6b7c8d9
Revises: d9b7e3a1c2f4
Create Date: 2026-04-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e3a4f6b7c8d9"
down_revision = "d9b7e3a1c2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "postbase_idempotency_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            "actor_user_id",
            "endpoint_fingerprint",
            name="uq_postbase_idempotency_key_actor_endpoint",
        ),
    )
    op.create_index(
        "ix_postbase_idempotency_record_actor_user_id",
        "postbase_idempotency_record",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_postbase_idempotency_record_created_at",
        "postbase_idempotency_record",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_postbase_idempotency_record_idempotency_key",
        "postbase_idempotency_record",
        ["idempotency_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_postbase_idempotency_record_idempotency_key", table_name="postbase_idempotency_record")
    op.drop_index("ix_postbase_idempotency_record_created_at", table_name="postbase_idempotency_record")
    op.drop_index("ix_postbase_idempotency_record_actor_user_id", table_name="postbase_idempotency_record")
    op.drop_table("postbase_idempotency_record")
