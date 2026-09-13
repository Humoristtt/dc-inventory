"""Protect procurement receipts from generic warehouse adjustment.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION protect_procurement_receipt_movement()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.movement_type IN ('CORRECTION', 'REVERSAL')
               AND EXISTS (
                   SELECT 1
                   FROM procurement_requests
                   WHERE final_movement_id = NEW.original_movement_id
                   FOR KEY SHARE
               ) THEN
                RAISE EXCEPTION 'procurement movement is protected'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_movements_protect_procurement_receipt
        BEFORE INSERT ON movements
        FOR EACH ROW
        EXECUTE FUNCTION protect_procurement_receipt_movement()
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    op.execute("LOCK TABLE procurement_requests, movements IN ACCESS EXCLUSIVE MODE")
    if connection.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM procurement_requests WHERE final_movement_id IS NOT NULL)"
        )
    ).scalar():
        raise RuntimeError(
            "procurement receipt protection downgrade refused: completed procurement exists"
        )

    op.execute("DROP TRIGGER trg_movements_protect_procurement_receipt ON movements")
    op.execute("DROP FUNCTION protect_procurement_receipt_movement()")
