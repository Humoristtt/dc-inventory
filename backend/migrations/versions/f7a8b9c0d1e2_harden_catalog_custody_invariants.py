"""Harden Catalog required attributes and custody DB invariants.

Revision ID: f7a8b9c0d1e2
Revises: f6a7b8c9d0e1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    missing_required = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM items i
            WHERE EXISTS (
                SELECT 1
                FROM category_attributes ca
                WHERE ca.category_id = i.category_id
                  AND ca.required
                  AND NOT EXISTS (
                      SELECT 1
                      FROM item_attribute_values iav
                      WHERE iav.item_id = i.id
                        AND iav.category_attribute_id = ca.id
                  )
            )
            """
        )
    ).scalar_one()

    if missing_required:
        raise RuntimeError(
            "catalog required-attribute invariant cannot be enabled: "
            f"{missing_required} existing items are incomplete"
        )

    ineligible_custody = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM user_item_custody_balances c
            JOIN users u
              ON u.id = c.user_id
            WHERE u.access_status <> 'APPROVED'
               OR u.role NOT IN ('ENGINEER', 'SENIOR_ENGINEER')
            """
        )
    ).scalar_one()

    if ineligible_custody:
        raise RuntimeError(
            "custody eligibility invariant cannot be enabled: "
            f"{ineligible_custody} existing custody rows are ineligible"
        )

    # Catalog completeness uses one advisory-lock namespace per category.
    # All participating mutation paths take the same lock before validating,
    # preventing concurrent required-schema/item write skew.
    op.execute(
        """
        CREATE FUNCTION enforce_item_required_attributes()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            current_category_id uuid;
        BEGIN
            SELECT category_id
            INTO current_category_id
            FROM items
            WHERE id = NEW.id;

            IF current_category_id IS NULL THEN
                RETURN NULL;
            END IF;

            PERFORM pg_advisory_xact_lock(
                hashtextextended(current_category_id::text, 61503)
            );

            IF EXISTS (
                SELECT 1
                FROM category_attributes ca
                WHERE ca.category_id = current_category_id
                  AND ca.required
                  AND NOT EXISTS (
                      SELECT 1
                      FROM item_attribute_values iav
                      WHERE iav.item_id = NEW.id
                        AND iav.category_attribute_id = ca.id
                  )
            ) THEN
                RAISE EXCEPTION
                    'item is missing required catalog attributes'
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
            trg_items_required_attributes
        AFTER INSERT OR UPDATE ON items
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_item_required_attributes()
        """
    )

    op.execute(
        """
        CREATE FUNCTION enforce_item_attribute_required_completeness()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            current_item_id uuid;
            current_category_id uuid;
            old_category_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                current_item_id := OLD.item_id;
            ELSE
                current_item_id := NEW.item_id;
            END IF;

            SELECT category_id
            INTO current_category_id
            FROM items
            WHERE id = current_item_id;

            IF current_category_id IS NOT NULL THEN
                PERFORM pg_advisory_xact_lock(
                    hashtextextended(current_category_id::text, 61503)
                );

                IF EXISTS (
                    SELECT 1
                    FROM category_attributes ca
                    WHERE ca.category_id = current_category_id
                      AND ca.required
                      AND NOT EXISTS (
                          SELECT 1
                          FROM item_attribute_values iav
                          WHERE iav.item_id = current_item_id
                            AND iav.category_attribute_id = ca.id
                      )
                ) THEN
                    RAISE EXCEPTION
                        'item is missing required catalog attributes'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            IF TG_OP = 'UPDATE'
               AND OLD.item_id IS DISTINCT FROM NEW.item_id THEN

                SELECT category_id
                INTO old_category_id
                FROM items
                WHERE id = OLD.item_id;

                IF old_category_id IS NOT NULL THEN
                    PERFORM pg_advisory_xact_lock(
                        hashtextextended(old_category_id::text, 61503)
                    );

                    IF EXISTS (
                        SELECT 1
                        FROM category_attributes ca
                        WHERE ca.category_id = old_category_id
                          AND ca.required
                          AND NOT EXISTS (
                              SELECT 1
                              FROM item_attribute_values iav
                              WHERE iav.item_id = OLD.item_id
                                AND iav.category_attribute_id = ca.id
                          )
                    ) THEN
                        RAISE EXCEPTION
                            'item is missing required catalog attributes'
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
            END IF;

            RETURN NULL;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
            trg_item_attribute_values_required_attributes
        AFTER DELETE OR UPDATE ON item_attribute_values
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
            enforce_item_attribute_required_completeness()
        """
    )

    op.execute(
        """
        CREATE FUNCTION enforce_category_required_attributes()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.category_id::text, 61503)
            );

            IF EXISTS (
                SELECT 1
                FROM items i
                WHERE i.category_id = NEW.category_id
                  AND EXISTS (
                      SELECT 1
                      FROM category_attributes ca
                      WHERE ca.category_id = i.category_id
                        AND ca.required
                        AND NOT EXISTS (
                            SELECT 1
                            FROM item_attribute_values iav
                            WHERE iav.item_id = i.id
                              AND iav.category_attribute_id = ca.id
                        )
                  )
            ) THEN
                RAISE EXCEPTION
                    'category has items missing required attributes'
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
            trg_category_attributes_required_attributes
        AFTER INSERT OR UPDATE ON category_attributes
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_category_required_attributes()
        """
    )

    # Custody uses one advisory-lock namespace per user. A custody row and
    # a role/access mutation therefore cannot commit concurrently into an
    # invalid holder state.
    op.execute(
        """
        CREATE FUNCTION enforce_custody_holder_eligibility()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.user_id::text, 61504)
            );

            IF NOT EXISTS (
                SELECT 1
                FROM users
                WHERE id = NEW.user_id
                  AND access_status = 'APPROVED'
                  AND role IN ('ENGINEER', 'SENIOR_ENGINEER')
            ) THEN
                RAISE EXCEPTION
                    'custody holder must be an approved custody role'
                    USING ERRCODE = '23514';
            END IF;

            RETURN NEW;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TRIGGER
            trg_user_item_custody_validate_holder
        BEFORE INSERT OR UPDATE ON user_item_custody_balances
        FOR EACH ROW
        EXECUTE FUNCTION enforce_custody_holder_eligibility()
        """
    )

    op.execute(
        """
        CREATE FUNCTION enforce_user_custody_eligibility()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF OLD.role IS NOT DISTINCT FROM NEW.role
               AND OLD.access_status
                   IS NOT DISTINCT FROM NEW.access_status THEN
                RETURN NULL;
            END IF;

            PERFORM pg_advisory_xact_lock(
                hashtextextended(NEW.id::text, 61504)
            );

            IF (
                NEW.access_status <> 'APPROVED'
                OR NEW.role NOT IN ('ENGINEER', 'SENIOR_ENGINEER')
            )
            AND EXISTS (
                SELECT 1
                FROM user_item_custody_balances
                WHERE user_id = NEW.id
            ) THEN
                RAISE EXCEPTION
                    'user with custody must remain eligible'
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
            trg_users_validate_custody_eligibility
        AFTER UPDATE ON users
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION enforce_user_custody_eligibility()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_users_validate_custody_eligibility
        ON users
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_user_custody_eligibility()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_user_item_custody_validate_holder
        ON user_item_custody_balances
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_custody_holder_eligibility()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_category_attributes_required_attributes
        ON category_attributes
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_category_required_attributes()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_item_attribute_values_required_attributes
        ON item_attribute_values
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_item_attribute_required_completeness()
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
            trg_items_required_attributes
        ON items
        """
    )
    op.execute(
        """
        DROP FUNCTION IF EXISTS
            enforce_item_required_attributes()
        """
    )
