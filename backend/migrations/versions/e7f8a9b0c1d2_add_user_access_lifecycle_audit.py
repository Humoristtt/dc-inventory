"""add user access lifecycle audit

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | Sequence[str] | None = "d6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    access_type = sa.Enum(
        "PENDING",
        "APPROVED",
        "REJECTED",
        "BLOCKED",
        name="user_access_status",
        native_enum=False,
        create_constraint=False,
    )

    op.create_table(
        "user_access_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("before_access_status", access_type, nullable=False),
        sa.Column("after_access_status", access_type, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "before_access_status <> after_access_status",
            name=op.f(
                "ck_user_access_events_user_access_event_changed"
            ),
        ),
        sa.CheckConstraint(
            "before_access_status IN "
            "('PENDING', 'APPROVED', 'REJECTED', 'BLOCKED')",
            name=op.f(
                "ck_user_access_events_user_access_event_before_status"
            ),
        ),
        sa.CheckConstraint(
            "after_access_status IN "
            "('PENDING', 'APPROVED', 'REJECTED', 'BLOCKED')",
            name=op.f(
                "ck_user_access_events_user_access_event_after_status"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f(
                "fk_user_access_events_actor_user_id_users"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f(
                "fk_user_access_events_target_user_id_users"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_user_access_events"),
        ),
    )

    op.create_index(
        "ix_user_access_events_target_occurred",
        "user_access_events",
        ["target_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_user_access_events_actor_occurred",
        "user_access_events",
        ["actor_user_id", "occurred_at"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_user_access_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'user_access_events is append-only'
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_user_access_events_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE
        ON user_access_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION reject_user_access_event_mutation();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.execute(
        "LOCK TABLE user_access_events IN ACCESS EXCLUSIVE MODE"
    )

    if connection.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM user_access_events)"
        )
    ).scalar():
        raise RuntimeError(
            "user access audit downgrade refused: "
            "user_access_events contains immutable audit history"
        )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_user_access_events_append_only
        ON user_access_events;
        """
    )
    op.execute(
        "DROP FUNCTION IF EXISTS reject_user_access_event_mutation();"
    )

    op.drop_index(
        "ix_user_access_events_actor_occurred",
        table_name="user_access_events",
    )
    op.drop_index(
        "ix_user_access_events_target_occurred",
        table_name="user_access_events",
    )
    op.drop_table("user_access_events")
