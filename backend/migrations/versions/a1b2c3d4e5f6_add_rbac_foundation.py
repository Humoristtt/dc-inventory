"""add capability-based RBAC foundation

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0c1d2e3
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ROLES = (
    "ENGINEER",
    "SENIOR_ENGINEER",
    "MANAGER",
    "ADMIN",
    "OWNER",
)
_ROLE_VALUES = ", ".join(f"'{role}'" for role in _ROLES)


def _install_custody_function(*, legacy: bool) -> None:
    custody_roles = "('USER')" if legacy else "('ENGINEER', 'SENIOR_ENGINEER')"
    administrative_roles = "('ADMIN')" if legacy else "('ADMIN', 'OWNER')"
    actor_role_length = 5 if legacy else 15
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION validate_movement_custody()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            original_custody uuid;
            original_type varchar(10);
            actor_role varchar({actor_role_length});
        BEGIN
            IF NEW.custody_user_id IS NOT NULL
               AND NEW.movement_type NOT IN ('ISSUE', 'RETURN', 'REVERSAL')
            THEN
                RAISE EXCEPTION
                    'custody is only valid for issue, return, or reversal'
                    USING ERRCODE = '23514';
            END IF;

            IF NEW.movement_type IN ('ISSUE', 'RETURN') THEN
                SELECT role INTO actor_role
                FROM users
                WHERE id = NEW.actor_user_id;

                IF actor_role IN {custody_roles}
                   AND NEW.custody_user_id IS DISTINCT FROM NEW.actor_user_id
                THEN
                    RAISE EXCEPTION
                        'user issue/return custody must match movement actor'
                        USING ERRCODE = '23514';
                END IF;

                IF actor_role IN {administrative_roles}
                   AND NEW.custody_user_id IS NOT NULL
                THEN
                    RAISE EXCEPTION
                        'admin issue/return must not carry custody'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            IF NEW.movement_type = 'CORRECTION' THEN
                SELECT custody_user_id
                INTO original_custody
                FROM movements
                WHERE id = NEW.original_movement_id;

                IF original_custody IS NOT NULL THEN
                    RAISE EXCEPTION
                        'correction of custody movement is forbidden'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            IF NEW.movement_type = 'REVERSAL' THEN
                SELECT custody_user_id, movement_type
                INTO original_custody, original_type
                FROM movements
                WHERE id = NEW.original_movement_id;

                IF NOT FOUND THEN
                    RAISE EXCEPTION
                        'reversal original movement not found'
                        USING ERRCODE = '23514';
                END IF;

                IF NEW.custody_user_id IS DISTINCT FROM original_custody THEN
                    RAISE EXCEPTION
                        'reversal custody must match original movement'
                        USING ERRCODE = '23514';
                END IF;

                IF NEW.custody_user_id IS NOT NULL
                   AND original_type NOT IN ('ISSUE', 'RETURN')
                THEN
                    RAISE EXCEPTION
                        'custody reversal requires issue or return original'
                        USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )


def upgrade() -> None:
    op.execute("LOCK TABLE users, movements IN ACCESS EXCLUSIVE MODE")

    op.drop_constraint(op.f("ck_users_user_role"), "users", type_="check")
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=5),
        type_=sa.String(length=15),
        existing_nullable=False,
        existing_server_default=sa.text("'USER'::character varying"),
    )
    op.execute("UPDATE users SET role = 'ENGINEER' WHERE role = 'USER'")
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=15),
        existing_nullable=False,
        server_default=sa.text("'ENGINEER'"),
    )
    op.create_check_constraint(
        op.f("ck_users_user_role"),
        "users",
        f"role IN ({_ROLE_VALUES})",
    )
    op.create_index(
        "ux_users_singleton_owner",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'OWNER'"),
    )

    role_type = sa.Enum(
        *_ROLES,
        name="user_role",
        native_enum=False,
        create_constraint=False,
    )
    op.create_table(
        "user_role_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column("before_role", role_type, nullable=False),
        sa.Column("after_role", role_type, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "before_role <> after_role",
            name=op.f("ck_user_role_events_user_role_event_changed"),
        ),
        sa.CheckConstraint(
            f"before_role IN ({_ROLE_VALUES})",
            name=op.f("ck_user_role_events_user_role_event_before_role"),
        ),
        sa.CheckConstraint(
            f"after_role IN ({_ROLE_VALUES})",
            name=op.f("ck_user_role_events_user_role_event_after_role"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_user_role_events_actor_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_user_id"],
            ["users.id"],
            name=op.f("fk_user_role_events_target_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_role_events")),
    )
    op.create_index(
        "ix_user_role_events_target_occurred",
        "user_role_events",
        ["target_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_user_role_events_actor_occurred",
        "user_role_events",
        ["actor_user_id", "occurred_at"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_user_role_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'user_role_events is append-only'
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_user_role_events_append_only
        BEFORE UPDATE OR DELETE OR TRUNCATE
        ON user_role_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION reject_user_role_event_mutation();
        """
    )
    _install_custody_function(legacy=False)


def downgrade() -> None:
    connection = op.get_bind()
    op.execute(
        "LOCK TABLE users, movements, user_role_events "
        "IN ACCESS EXCLUSIVE MODE"
    )

    unsupported = connection.execute(
        sa.text(
            "SELECT role FROM users "
            "WHERE role NOT IN ('ENGINEER', 'ADMIN') "
            "ORDER BY role LIMIT 1"
        )
    ).scalar()
    if unsupported is not None:
        raise RuntimeError(
            "RBAC downgrade refused: role "
            f"{unsupported!r} is not representable by USER/ADMIN"
        )

    if connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM user_role_events)")
    ).scalar():
        raise RuntimeError(
            "RBAC downgrade refused: user_role_events contains immutable audit history"
        )

    _install_custody_function(legacy=True)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_user_role_events_append_only "
        "ON user_role_events"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_user_role_event_mutation()")
    op.drop_index(
        "ix_user_role_events_actor_occurred",
        table_name="user_role_events",
    )
    op.drop_index(
        "ix_user_role_events_target_occurred",
        table_name="user_role_events",
    )
    op.drop_table("user_role_events")

    op.drop_index("ux_users_singleton_owner", table_name="users")
    op.drop_constraint(op.f("ck_users_user_role"), "users", type_="check")
    op.execute("UPDATE users SET role = 'USER' WHERE role = 'ENGINEER'")
    op.alter_column(
        "users",
        "role",
        existing_type=sa.String(length=15),
        type_=sa.String(length=5),
        existing_nullable=False,
        server_default=sa.text("'USER'"),
    )
    op.create_check_constraint(
        op.f("ck_users_user_role"),
        "users",
        "role IN ('USER', 'ADMIN')",
    )
