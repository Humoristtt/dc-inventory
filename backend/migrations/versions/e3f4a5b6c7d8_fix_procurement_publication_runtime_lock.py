"""Keep Procurement publication guard compatible with runtime grants.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d2e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Publication already serializes with revision-line INSERT through the
    # shared advisory transaction lock. A row locking clause on the immutable
    # revision header is therefore unnecessary and would additionally require
    # UPDATE privilege from the least-privilege runtime principal.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_procurement_revision_publication()
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
            WHERE id = NEW.revision_id;

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


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_procurement_revision_publication()
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
