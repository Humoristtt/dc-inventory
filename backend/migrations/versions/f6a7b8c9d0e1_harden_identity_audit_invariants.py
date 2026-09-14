"""Harden identity OWNER and DB-coupled audit invariants.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # OWNER is the recovery/security principal and must never exist in a
    # non-approved lifecycle state, regardless of the application path.
    op.create_check_constraint(
        op.f("ck_users_owner_must_be_approved"),
        "users",
        "role <> 'OWNER' OR access_status = 'APPROVED'",
    )

    # Every identity audit row records the PostgreSQL transaction which
    # produced it. This lets deferred constraint triggers prove that the
    # corresponding users mutation and immutable audit row are atomic.
    op.add_column(
        "user_access_events",
        sa.Column(
            "db_transaction_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("txid_current()"),
        ),
    )
    op.add_column(
        "user_role_events",
        sa.Column(
            "db_transaction_id",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("txid_current()"),
        ),
    )

    op.create_index(
        "ix_user_access_events_target_txid",
        "user_access_events",
        ["target_user_id", "db_transaction_id"],
    )
    op.create_index(
        "ix_user_role_events_target_txid",
        "user_role_events",
        ["target_user_id", "db_transaction_id"],
    )

    op.execute(
        """
        CREATE FUNCTION enforce_user_access_audit_coupling()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.access_status IS NOT DISTINCT FROM NEW.access_status THEN
                RETURN NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM user_access_events
                WHERE target_user_id = NEW.id
                  AND before_access_status = OLD.access_status
                  AND after_access_status = NEW.access_status
                  AND db_transaction_id = txid_current()
            ) THEN
                RAISE EXCEPTION
                    'users.access_status mutation requires '
                    'same-transaction audit event'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            trg_users_require_access_audit
        AFTER UPDATE ON users
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_user_access_audit_coupling()
        """
    )

    op.execute(
        """
        CREATE FUNCTION enforce_user_role_audit_coupling()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.role IS NOT DISTINCT FROM NEW.role THEN
                RETURN NULL;
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM user_role_events
                WHERE target_user_id = NEW.id
                  AND before_role = OLD.role
                  AND after_role = NEW.role
                  AND db_transaction_id = txid_current()
            ) THEN
                RAISE EXCEPTION
                    'users.role mutation requires '
                    'same-transaction audit event'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            trg_users_require_role_audit
        AFTER UPDATE ON users
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_user_role_audit_coupling()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_users_require_role_audit
        ON users
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_user_role_audit_coupling()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_users_require_access_audit
        ON users
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_user_access_audit_coupling()
        """
    )

    op.drop_index(
        "ix_user_role_events_target_txid",
        table_name="user_role_events",
    )
    op.drop_index(
        "ix_user_access_events_target_txid",
        table_name="user_access_events",
    )

    op.drop_column(
        "user_role_events",
        "db_transaction_id",
    )
    op.drop_column(
        "user_access_events",
        "db_transaction_id",
    )

    op.drop_constraint(
        op.f("ck_users_owner_must_be_approved"),
        "users",
        type_="check",
    )
