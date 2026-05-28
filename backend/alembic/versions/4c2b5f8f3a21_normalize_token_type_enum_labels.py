"""normalize token type enum labels

Revision ID: 4c2b5f8f3a21
Revises: 8f1c6d4b2a7e
Create Date: 2026-05-26 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4c2b5f8f3a21'
down_revision: Union[str, Sequence[str], None] = '8f1c6d4b2a7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_enum_label(enum_name: str, old_label: str, new_label: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = '{enum_name}'
                  AND e.enumlabel = '{old_label}'
            ) AND NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = '{enum_name}'
                  AND e.enumlabel = '{new_label}'
            ) THEN
                EXECUTE 'ALTER TYPE {enum_name} RENAME VALUE ''{old_label}'' TO ''{new_label}''';
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    _rename_enum_label('tokentype', 'ACCESS', 'access')
    _rename_enum_label('tokentype', 'REFRESH', 'refresh')
    _rename_enum_label('tokentype', 'PASSWORD_RESET', 'password_reset')
    _rename_enum_label('tokentype', 'EMAIL_VERIFICATION', 'email_verification')
    _rename_enum_label('tokentype', 'TEMP_AUTH', 'temp_auth')
    _rename_enum_label('tokentype', 'BEARER', 'bearer')
    _rename_enum_label('tokentype', 'IP_WHITELIST', 'ip_whitelist')
    _rename_enum_label('tokentype', 'IP_BLACKLIST', 'ip_blacklist')


def downgrade() -> None:
    _rename_enum_label('tokentype', 'access', 'ACCESS')
    _rename_enum_label('tokentype', 'refresh', 'REFRESH')
    _rename_enum_label('tokentype', 'password_reset', 'PASSWORD_RESET')
    _rename_enum_label('tokentype', 'email_verification', 'EMAIL_VERIFICATION')
    _rename_enum_label('tokentype', 'temp_auth', 'TEMP_AUTH')
    _rename_enum_label('tokentype', 'bearer', 'BEARER')
    _rename_enum_label('tokentype', 'ip_whitelist', 'IP_WHITELIST')
    _rename_enum_label('tokentype', 'ip_blacklist', 'IP_BLACKLIST')