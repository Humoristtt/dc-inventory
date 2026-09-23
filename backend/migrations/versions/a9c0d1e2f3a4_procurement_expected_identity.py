"""Persist canonical Procurement expected item identity.

Revision ID: a9c0d1e2f3a4
Revises: f8b9c0d1e2f3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9c0d1e2f3a4"
down_revision = "f8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "procurement_revision_lines",
        sa.Column(
            "expected_identity_signature",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.execute(
        """
        LOCK TABLE procurement_revision_lines
        IN ACCESS EXCLUSIVE MODE
        """
    )

    op.execute(
        """
        ALTER TABLE procurement_revision_lines
        DISABLE TRIGGER
        trg_procurement_revision_lines_append_only
        """
    )

    op.execute(
        """
        WITH snapshot_lines AS (
            SELECT
                line.id AS line_id,
                line.display_snapshot,
                category.id AS category_id,
                category.key AS category_key
            FROM procurement_revision_lines AS line
            JOIN categories AS category
              ON category.key =
                 line.display_snapshot ->> 'category_key'
            WHERE line.expected_identity_signature IS NULL
              AND jsonb_typeof(
                  line.display_snapshot -> 'category_key'
              ) = 'string'
              AND (
                  NOT (line.display_snapshot ? 'manufacturer_name')
                  OR jsonb_typeof(
                      line.display_snapshot -> 'manufacturer_name'
                  ) IN ('string', 'null')
              )
              AND (
                  NOT (line.display_snapshot ? 'model')
                  OR jsonb_typeof(
                      line.display_snapshot -> 'model'
                  ) IN ('string', 'null')
              )
              AND jsonb_typeof(
                  line.display_snapshot -> 'attributes'
              ) = 'object'
        ),
        attribute_parts AS (
            SELECT
                snapshot.line_id,
                count(*) AS supplied_count,
                count(attribute.id) AS known_count,
                bool_and(
                    CASE attribute.data_type
                        WHEN 'TEXT'
                            THEN jsonb_typeof(entry.value) = 'string'
                              AND catalog_identity_text(
                                  entry.value #>> '{}'
                              ) <> ''
                        WHEN 'ENUM'
                            THEN jsonb_typeof(entry.value) = 'string'
                              AND catalog_identity_text(
                                  entry.value #>> '{}'
                              ) <> ''
                        WHEN 'INTEGER'
                            THEN jsonb_typeof(entry.value) = 'number'
                              AND entry.value::text ~ '^-?(0|[1-9][0-9]*)$'
                              AND abs(
                                  (entry.value #>> '{}')::numeric
                              ) <= 9007199254740991
                        WHEN 'DECIMAL'
                            THEN jsonb_typeof(entry.value) = 'string'
                              AND (entry.value #>> '{}') ~
                                  '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$'
                        WHEN 'BOOLEAN'
                            THEN jsonb_typeof(entry.value) = 'boolean'
                        ELSE false
                    END
                ) AS valid_values,
                string_agg(
                    to_json(entry.key)::text
                    || ':'
                    || CASE attribute.data_type
                        WHEN 'TEXT' THEN
                            CASE
                                WHEN jsonb_typeof(entry.value) = 'string'
                                THEN to_json(
                                    catalog_identity_text(
                                        entry.value #>> '{}'
                                    )
                                )::text
                            END
                        WHEN 'ENUM' THEN
                            CASE
                                WHEN jsonb_typeof(entry.value) = 'string'
                                THEN to_json(
                                    catalog_identity_text(
                                        entry.value #>> '{}'
                                    )
                                )::text
                            END
                        WHEN 'INTEGER' THEN
                            CASE
                                WHEN jsonb_typeof(entry.value) = 'number'
                                THEN (
                                    (
                                        entry.value #>> '{}'
                                    )::bigint
                                )::text
                            END
                        WHEN 'DECIMAL' THEN
                            CASE
                                WHEN jsonb_typeof(entry.value) = 'string'
                                THEN to_json(
                                    catalog_decimal_identity(
                                        (
                                            entry.value #>> '{}'
                                        )::numeric
                                    )
                                )::text
                            END
                        WHEN 'BOOLEAN' THEN
                            CASE
                                WHEN jsonb_typeof(entry.value) = 'boolean'
                                THEN CASE
                                    WHEN (
                                        entry.value #>> '{}'
                                    )::boolean
                                    THEN 'true'
                                    ELSE 'false'
                                END
                            END
                    END,
                    ','
                    ORDER BY entry.key COLLATE "C"
                ) AS attributes_json
            FROM snapshot_lines AS snapshot
            CROSS JOIN LATERAL jsonb_each(
                snapshot.display_snapshot -> 'attributes'
            ) AS entry(key, value)
            LEFT JOIN category_attributes AS attribute
              ON attribute.category_id = snapshot.category_id
             AND attribute.key = entry.key
            GROUP BY snapshot.line_id
        ),
        reconstructed AS (
            SELECT
                snapshot.line_id,
                encode(
                    sha256(
                        convert_to(
                            '['
                            || to_json(
                                snapshot.category_key
                            )::text
                            || ','
                            || to_json(
                                catalog_identity_text(
                                    coalesce(
                                        snapshot.display_snapshot
                                            ->> 'manufacturer_name',
                                        ''
                                    )
                                )
                            )::text
                            || ','
                            || to_json(
                                catalog_identity_text(
                                    coalesce(
                                        snapshot.display_snapshot
                                            ->> 'model',
                                        ''
                                    )
                                )
                            )::text
                            || ',{'
                            || coalesce(
                                parts.attributes_json,
                                ''
                            )
                            || '}]',
                            'UTF8'
                        )
                    ),
                    'hex'
                ) AS identity_signature
            FROM snapshot_lines AS snapshot
            LEFT JOIN attribute_parts AS parts
              ON parts.line_id = snapshot.line_id
            WHERE coalesce(
                parts.supplied_count,
                0
            ) = coalesce(
                parts.known_count,
                0
            )
              AND coalesce(
                  parts.valid_values,
                  true
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM category_attributes AS required_attribute
                  WHERE required_attribute.category_id = snapshot.category_id
                    AND required_attribute.required
                    AND NOT (
                        snapshot.display_snapshot -> 'attributes'
                        ? required_attribute.key
                    )
              )
        )
        UPDATE procurement_revision_lines AS line
        SET expected_identity_signature =
            reconstructed.identity_signature
        FROM reconstructed
        WHERE reconstructed.line_id = line.id
          AND line.expected_identity_signature IS NULL
          AND (
              NOT (line.display_snapshot ? 'identity_signature')
              OR (
                  jsonb_typeof(
                      line.display_snapshot -> 'identity_signature'
                  ) = 'string'
                  AND line.display_snapshot ->> 'identity_signature'
                      = reconstructed.identity_signature
              )
          )
        """
    )

    connection = op.get_bind()

    unresolved = int(
        connection.execute(
            sa.text(
                """
                SELECT count(*)
                FROM procurement_revision_lines
                WHERE expected_identity_signature IS NULL
                """
            )
        ).scalar_one()
    )

    if unresolved:
        raise RuntimeError(
            "cannot safely reconstruct canonical identity "
            "from immutable Procurement snapshot for "
            f"{unresolved} historical line(s); "
            "repair the historical snapshot before applying "
            "a9c0d1e2f3a4"
        )

    op.alter_column(
        "procurement_revision_lines",
        "expected_identity_signature",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.create_check_constraint(
        op.f("ck_procurement_revision_lines_expected_identity_sig_len"),
        "procurement_revision_lines",
        "expected_identity_signature ~ '^[0-9a-f]{64}$'",
    )
    op.execute(
        """
        ALTER TABLE procurement_revision_lines
        ENABLE TRIGGER
        trg_procurement_revision_lines_append_only
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_procurement_revision_lines_expected_identity_sig_len"),
        "procurement_revision_lines",
        type_="check",
    )

    op.drop_column(
        "procurement_revision_lines",
        "expected_identity_signature",
    )
