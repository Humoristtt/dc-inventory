"""Harden Procurement revision sealing and receipt binding invariants.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A revision is considered published once REQUEST_CREATED or
    # REVISION_SUBMITTED exists for it.
    #
    # Line INSERT and publication both serialize on the same advisory
    # transaction lock. This closes both sequential late INSERT and the
    # concurrent "insert while revision is being published" shape.
    op.execute(
        """
        CREATE FUNCTION protect_procurement_revision_line_insert()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.revision_id::text, 61501)
            );

            IF EXISTS (
                SELECT 1
                FROM procurement_events
                WHERE revision_id = NEW.revision_id
                  AND event_type IN (
                      'REQUEST_CREATED',
                      'REVISION_SUBMITTED'
                  )
            ) THEN
                RAISE EXCEPTION
                    'procurement revision is sealed'
                    USING ERRCODE = '55000';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_procurement_revision_lines_sealed_insert
        BEFORE INSERT ON procurement_revision_lines
        FOR EACH ROW
        EXECUTE FUNCTION protect_procurement_revision_line_insert()
        """
    )

    # Publication takes the same revision lock and proves that the immutable
    # line set is complete before the publication event becomes durable.
    op.execute(
        """
        CREATE FUNCTION validate_procurement_revision_publication()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            expected_line_count integer;
            actual_line_count bigint;
        BEGIN
            IF NEW.revision_id IS NULL
               OR NEW.event_type NOT IN (
                   'REQUEST_CREATED',
                   'REVISION_SUBMITTED'
               ) THEN
                RETURN NEW;
            END IF;

            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.revision_id::text, 61501)
            );

            SELECT line_count
            INTO expected_line_count
            FROM procurement_revisions
            WHERE id = NEW.revision_id
            FOR KEY SHARE;

            IF expected_line_count IS NULL THEN
                RAISE EXCEPTION
                    'procurement publication references unknown revision'
                    USING ERRCODE = '23503';
            END IF;

            SELECT count(*)
            INTO actual_line_count
            FROM procurement_revision_lines
            WHERE revision_id = NEW.revision_id;

            IF actual_line_count <> expected_line_count THEN
                RAISE EXCEPTION
                    'procurement revision line count mismatch'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_procurement_events_validate_revision_publication
        BEFORE INSERT ON procurement_events
        FOR EACH ROW
        EXECUTE FUNCTION validate_procurement_revision_publication()
        """
    )

    # Strengthen the d4 movement-side protection. Both movement adjustment
    # and final Procurement binding serialize on the same movement-specific
    # advisory transaction lock.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_procurement_receipt_movement()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.movement_type IN ('CORRECTION', 'REVERSAL')
               AND NEW.original_movement_id IS NOT NULL THEN

                PERFORM pg_advisory_xact_lock(
                    hashtextextended(
                        NEW.original_movement_id::text,
                        61502
                    )
                );

                IF EXISTS (
                    SELECT 1
                    FROM procurement_requests
                    WHERE final_movement_id = NEW.original_movement_id
                ) THEN
                    RAISE EXCEPTION
                        'procurement movement is protected'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE FUNCTION protect_procurement_final_movement_binding()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.final_movement_id IS NOT NULL
               AND (
                   TG_OP = 'INSERT'
                   OR OLD.final_movement_id
                      IS DISTINCT FROM NEW.final_movement_id
               ) THEN

                PERFORM pg_advisory_xact_lock(
                    hashtextextended(
                        NEW.final_movement_id::text,
                        61502
                    )
                );

                IF EXISTS (
                    SELECT 1
                    FROM movements
                    WHERE original_movement_id
                          = NEW.final_movement_id
                      AND movement_type IN (
                          'CORRECTION',
                          'REVERSAL'
                      )
                ) THEN
                    RAISE EXCEPTION
                        'adjusted movement cannot become procurement receipt'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_procurement_requests_protect_final_movement
        BEFORE INSERT OR UPDATE ON procurement_requests
        FOR EACH ROW
        EXECUTE FUNCTION protect_procurement_final_movement_binding()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_procurement_requests_protect_final_movement
        ON procurement_requests
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            protect_procurement_final_movement_binding()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_procurement_receipt_movement()
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
                RAISE EXCEPTION
                    'procurement movement is protected'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_procurement_events_validate_revision_publication
        ON procurement_events
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            validate_procurement_revision_publication()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_procurement_revision_lines_sealed_insert
        ON procurement_revision_lines
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            protect_procurement_revision_line_insert()
        """
    )
