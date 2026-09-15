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
        UPDATE procurement_revision_lines AS line
        SET expected_identity_signature =
            item.identity_signature
        FROM items AS item
        WHERE line.catalog_item_id = item.id
          AND line.expected_identity_signature IS NULL
        """
    )

    op.execute(
        """
        UPDATE procurement_revision_lines AS line
        SET expected_identity_signature =
            item.identity_signature
        FROM procurement_line_catalog_bindings AS binding
        JOIN items AS item
          ON item.id = binding.item_id
        WHERE binding.revision_line_id = line.id
          AND line.expected_identity_signature IS NULL
        """
    )

    op.execute(
        """
        UPDATE procurement_revision_lines
        SET expected_identity_signature =
            display_snapshot ->> 'identity_signature'
        WHERE expected_identity_signature IS NULL
          AND display_snapshot ? 'identity_signature'
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
            "cannot safely infer canonical identity for "
            f"{unresolved} historical Procurement line(s); "
            "resolve or bind those lines before applying "
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
        "char_length(expected_identity_signature) = 64",
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
