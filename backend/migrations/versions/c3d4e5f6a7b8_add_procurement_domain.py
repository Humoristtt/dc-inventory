"""add procurement domain and email outbox

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE procurement_request_number_seq START WITH 1 INCREMENT BY 1")
    op.create_table(
        "procurement_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_number", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default=sa.text("'AGREEMENT_PENDING_MANAGER'"),
            nullable=False,
        ),
        sa.Column("initiator_user_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_manager_user_id", sa.Uuid(), nullable=False),
        sa.Column("creation_client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("current_revision_id", sa.Uuid(), nullable=False),
        sa.Column("final_movement_id", sa.Uuid(), nullable=True),
        sa.Column("state_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "btrim(request_number) <> ''",
            name=op.f("ck_procurement_requests_request_number_not_blank"),
        ),
        sa.CheckConstraint(
            "status IN ('AGREEMENT_PENDING_MANAGER', 'AGREEMENT_REVISION_REQUIRED', "
            "'PURCHASING', 'AWAITING_ACCEPTANCE', 'COMPLETED')",
            name=op.f("ck_procurement_requests_status"),
        ),
        sa.CheckConstraint(
            "state_version >= 1", name=op.f("ck_procurement_requests_state_version_positive")
        ),
        sa.CheckConstraint(
            "btrim(creation_client_request_id) <> ''",
            name=op.f("ck_procurement_requests_creation_client_request_id_not_blank"),
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name=op.f("ck_procurement_requests_request_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND final_movement_id IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND final_movement_id IS NULL AND completed_at IS NULL)",
            name=op.f("ck_procurement_requests_completion_state"),
        ),
        sa.ForeignKeyConstraint(
            ["initiator_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_requests_initiator_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_manager_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_requests_assigned_manager_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["final_movement_id"],
            ["movements.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_requests_final_movement_id_movements"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_requests")),
        sa.UniqueConstraint("request_number", name=op.f("uq_procurement_requests_request_number")),
        sa.UniqueConstraint(
            "final_movement_id", name=op.f("uq_procurement_requests_final_movement_id")
        ),
        sa.UniqueConstraint(
            "initiator_user_id",
            "creation_client_request_id",
            name="uq_procurement_requests_initiator_client_request",
        ),
    )
    op.create_index(
        "ix_procurement_requests_status_created", "procurement_requests", ["status", "created_at"]
    )
    op.create_index(
        "ix_procurement_requests_initiator_created",
        "procurement_requests",
        ["initiator_user_id", "created_at"],
    )
    op.create_index(
        "ix_procurement_requests_manager_status_created",
        "procurement_requests",
        ["assigned_manager_user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_procurement_requests_created_at_id", "procurement_requests", ["created_at", "id"]
    )
    op.create_index(
        "ix_procurement_requests_current_revision_id",
        "procurement_requests",
        ["current_revision_id"],
    )
    op.create_index(
        "ix_procurement_requests_active_queue",
        "procurement_requests",
        ["status", "updated_at"],
        postgresql_where=sa.text("status <> 'COMPLETED'"),
    )

    op.create_table(
        "procurement_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("submitted_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_by_display_name_snapshot", sa.String(length=579), nullable=False),
        sa.Column("general_comment", sa.Text(), nullable=True),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "revision_number > 0", name=op.f("ck_procurement_revisions_revision_number_positive")
        ),
        sa.CheckConstraint(
            "line_count BETWEEN 1 AND 500", name=op.f("ck_procurement_revisions_line_count_range")
        ),
        sa.CheckConstraint(
            "general_comment IS NULL OR btrim(general_comment) <> ''",
            name=op.f("ck_procurement_revisions_general_comment_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["procurement_requests.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_revisions_request_id_procurement_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_revisions_submitted_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_revisions")),
        sa.UniqueConstraint("request_id", "revision_number", name="uq_procurement_revision_number"),
        sa.UniqueConstraint("id", "request_id", name="uq_procurement_revision_id_request_id"),
    )
    op.create_index(
        "ix_procurement_revisions_request_created",
        "procurement_revisions",
        ["request_id", "created_at"],
    )

    op.create_foreign_key(
        "fk_proc_requests_current_revision_proc_revisions",
        "procurement_requests",
        "procurement_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "procurement_revision_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("line_type", sa.String(length=16), nullable=False),
        sa.Column("catalog_item_id", sa.Uuid(), nullable=True),
        sa.Column("display_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "line_no > 0", name=op.f("ck_procurement_revision_lines_line_no_positive")
        ),
        sa.CheckConstraint(
            "quantity > 0", name=op.f("ck_procurement_revision_lines_quantity_positive")
        ),
        sa.CheckConstraint(
            "line_type IN ('EXISTING_ITEM', 'PROPOSED_ITEM')",
            name=op.f("ck_procurement_revision_lines_line_type"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(display_snapshot) = 'object'",
            name=op.f("ck_procurement_revision_lines_display_snapshot_object"),
        ),
        sa.CheckConstraint(
            "(line_type = 'EXISTING_ITEM' AND catalog_item_id IS NOT NULL) OR "
            "(line_type = 'PROPOSED_ITEM' AND catalog_item_id IS NULL)",
            name=op.f("ck_procurement_revision_lines_catalog_item_shape"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["procurement_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_revision_lines_revision_id_procurement_revisions"),
        ),
        sa.ForeignKeyConstraint(
            ["catalog_item_id"],
            ["items.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_revision_lines_catalog_item_id_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_revision_lines")),
        sa.UniqueConstraint("revision_id", "line_no", name="uq_procurement_revision_line_no"),
    )
    op.create_index(
        "ix_procurement_revision_lines_revision",
        "procurement_revision_lines",
        ["revision_id", "line_no"],
    )
    op.create_index(
        "ix_procurement_revision_lines_catalog_item",
        "procurement_revision_lines",
        ["catalog_item_id"],
    )

    op.create_table(
        "procurement_line_catalog_bindings",
        sa.Column("revision_line_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("bound_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "bound_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["revision_line_id"],
            ["procurement_revision_lines.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_procurement_line_catalog_bindings_revision_line_id_procurement_revision_lines"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_line_catalog_bindings_item_id_items"),
        ),
        sa.ForeignKeyConstraint(
            ["bound_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_line_catalog_bindings_bound_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint(
            "revision_line_id", name=op.f("pk_procurement_line_catalog_bindings")
        ),
    )
    op.create_index(
        "ix_procurement_line_catalog_bindings_item",
        "procurement_line_catalog_bindings",
        ["item_id"],
    )

    op.create_table(
        "procurement_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=31), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_display_name_snapshot", sa.String(length=579), nullable=False),
        sa.Column("client_request_id", sa.String(length=128), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=30), nullable=True),
        sa.Column("to_status", sa.String(length=30), nullable=True),
        sa.Column("revision_id", sa.Uuid(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "event_type IN ('REQUEST_CREATED', 'REVISION_SUBMITTED', 'MANAGER_ACCEPTED', "
            "'CORRECTION_REQUESTED', 'ASSIGNMENT_TAKEN', 'ASSIGNMENT_TRANSFERRED', "
            "'TRANSFERRED_TO_ACCEPTANCE', 'LINE_BOUND', 'DISCREPANCY_REPORTED', 'COMPLETED')",
            name=op.f("ck_procurement_events_event_type"),
        ),
        sa.CheckConstraint(
            "btrim(actor_display_name_snapshot) <> ''",
            name=op.f("ck_procurement_events_actor_not_blank"),
        ),
        sa.CheckConstraint(
            "btrim(client_request_id) <> ''",
            name=op.f("ck_procurement_events_client_request_id_not_blank"),
        ),
        sa.CheckConstraint(
            "length(request_fingerprint) = 64",
            name=op.f("ck_procurement_events_request_fingerprint_length"),
        ),
        sa.CheckConstraint(
            "comment IS NULL OR btrim(comment) <> ''",
            name=op.f("ck_procurement_events_comment_not_blank"),
        ),
        sa.CheckConstraint(
            "metadata IS NULL OR jsonb_typeof(metadata) = 'object'",
            name=op.f("ck_procurement_events_metadata_object"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["procurement_requests.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_events_request_id_procurement_requests"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_events_actor_user_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["procurement_revisions.id"],
            ondelete="RESTRICT",
            name=op.f("fk_procurement_events_revision_id_procurement_revisions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_procurement_events")),
        sa.UniqueConstraint(
            "request_id",
            "actor_user_id",
            "client_request_id",
            name="uq_procurement_events_request_actor_client_request",
        ),
    )
    op.create_index(
        "ix_procurement_events_request_occurred",
        "procurement_events",
        ["request_id", "occurred_at", "id"],
    )
    op.create_index(
        "ix_procurement_events_actor_occurred",
        "procurement_events",
        ["actor_user_id", "occurred_at"],
    )

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("to_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cc_addresses", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=8), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENT', 'DEAD')", name=op.f("ck_email_outbox_status")
        ),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_email_outbox_attempts_non_negative")),
        sa.CheckConstraint(
            "jsonb_typeof(to_addresses) = 'array'", name=op.f("ck_email_outbox_to_addresses_array")
        ),
        sa.CheckConstraint(
            "jsonb_typeof(cc_addresses) = 'array'", name=op.f("ck_email_outbox_cc_addresses_array")
        ),
        sa.CheckConstraint("btrim(subject) <> ''", name=op.f("ck_email_outbox_subject_not_blank")),
        sa.CheckConstraint(
            "btrim(text_body) <> ''", name=op.f("ck_email_outbox_text_body_not_blank")
        ),
        sa.CheckConstraint(
            "btrim(html_body) <> ''", name=op.f("ck_email_outbox_html_body_not_blank")
        ),
        sa.CheckConstraint(
            "(claimed_at IS NULL AND claim_token IS NULL) OR "
            "(claimed_at IS NOT NULL AND claim_token IS NOT NULL)",
            name=op.f("ck_email_outbox_claim_state"),
        ),
        sa.CheckConstraint(
            "(status = 'SENT' AND sent_at IS NOT NULL) OR (status <> 'SENT' AND sent_at IS NULL)",
            name=op.f("ck_email_outbox_sent_state"),
        ),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["procurement_requests.id"],
            ondelete="RESTRICT",
            name=op.f("fk_email_outbox_request_id_procurement_requests"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_outbox")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_email_outbox_dedupe_key")),
    )
    op.create_index(
        "ix_email_outbox_delivery", "email_outbox", ["status", "available_at", "claimed_at"]
    )
    op.create_index("ix_email_outbox_status_updated", "email_outbox", ["status", "updated_at"])

    op.execute(
        """
        CREATE FUNCTION reject_procurement_immutable_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'procurement history is append-only' USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    for table in (
        "procurement_revisions",
        "procurement_revision_lines",
        "procurement_line_catalog_bindings",
        "procurement_events",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table}_append_only BEFORE UPDATE OR DELETE OR TRUNCATE "
            f"ON {table} FOR EACH STATEMENT EXECUTE FUNCTION "
            "reject_procurement_immutable_mutation()"
        )
    op.execute(
        """
        CREATE FUNCTION validate_procurement_current_revision()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM procurement_revisions
                WHERE id = NEW.current_revision_id AND request_id = NEW.id
            ) THEN
                RAISE EXCEPTION 'current procurement revision must belong to request'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_procurement_current_revision "
        "AFTER INSERT OR UPDATE OF current_revision_id ON procurement_requests "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        "EXECUTE FUNCTION validate_procurement_current_revision()"
    )


def downgrade() -> None:
    connection = op.get_bind()
    op.execute(
        "LOCK TABLE procurement_requests, procurement_revisions, procurement_revision_lines, "
        "procurement_line_catalog_bindings, procurement_events, email_outbox "
        "IN ACCESS EXCLUSIVE MODE"
    )
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM procurement_requests)")).scalar():
        raise RuntimeError(
            "procurement downgrade refused: immutable procurement history cannot be represented"
        )
    op.execute("DROP TRIGGER IF EXISTS trg_procurement_current_revision ON procurement_requests")
    op.execute("DROP FUNCTION IF EXISTS validate_procurement_current_revision()")
    for table in (
        "procurement_events",
        "procurement_line_catalog_bindings",
        "procurement_revision_lines",
        "procurement_revisions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_procurement_immutable_mutation()")
    op.drop_index("ix_email_outbox_status_updated", table_name="email_outbox")
    op.drop_index("ix_email_outbox_delivery", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_index("ix_procurement_events_actor_occurred", table_name="procurement_events")
    op.drop_index("ix_procurement_events_request_occurred", table_name="procurement_events")
    op.drop_table("procurement_events")
    op.drop_index(
        "ix_procurement_line_catalog_bindings_item", table_name="procurement_line_catalog_bindings"
    )
    op.drop_table("procurement_line_catalog_bindings")
    op.drop_index(
        "ix_procurement_revision_lines_catalog_item", table_name="procurement_revision_lines"
    )
    op.drop_index("ix_procurement_revision_lines_revision", table_name="procurement_revision_lines")
    op.drop_table("procurement_revision_lines")
    op.drop_constraint(
        "fk_proc_requests_current_revision_proc_revisions",
        "procurement_requests",
        type_="foreignkey",
    )
    op.drop_index("ix_procurement_revisions_request_created", table_name="procurement_revisions")
    op.drop_table("procurement_revisions")
    op.drop_index("ix_procurement_requests_active_queue", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_current_revision_id", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_created_at_id", table_name="procurement_requests")
    op.drop_index(
        "ix_procurement_requests_manager_status_created", table_name="procurement_requests"
    )
    op.drop_index("ix_procurement_requests_initiator_created", table_name="procurement_requests")
    op.drop_index("ix_procurement_requests_status_created", table_name="procurement_requests")
    op.drop_table("procurement_requests")
    op.execute("DROP SEQUENCE procurement_request_number_seq")
