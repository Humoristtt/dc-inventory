"""add user item custody projection

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: str | Sequence[str] | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()

    op.execute("LOCK TABLE movements IN ACCESS EXCLUSIVE MODE")

    ambiguous = connection.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM movements
                WHERE movement_type IN ('ISSUE', 'RETURN')
            )
            """
        )
    ).scalar()

    if ambiguous:
        raise RuntimeError(
            "custody migration refused: existing ISSUE/RETURN history "
            "cannot be assigned to users unambiguously"
        )

    op.add_column(
        "movements",
        sa.Column("custody_user_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_movements_custody_user_id_users"),
        "movements",
        "users",
        ["custody_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_movements_custody_user_id"),
        "movements",
        ["custody_user_id"],
        unique=False,
    )
    op.create_check_constraint(
        op.f("ck_movements_custody_movement_type"),
        "movements",
        "custody_user_id IS NULL OR "
        "movement_type IN ('ISSUE', 'RETURN', 'REVERSAL')",
    )

    op.create_table(
        "user_item_custody_balances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name=op.f(
                "ck_user_item_custody_balances_quantity_positive"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f(
                "fk_user_item_custody_balances_user_id_users"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["item_id"],
            ["items.id"],
            name=op.f(
                "fk_user_item_custody_balances_item_id_items"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_user_item_custody_balances"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "item_id",
            name=op.f(
                "uq_user_item_custody_balances_user_id_item_id"
            ),
        ),
    )
    op.create_index(
        op.f("ix_user_item_custody_balances_item_id"),
        "user_item_custody_balances",
        ["item_id"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION validate_movement_custody()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            original_custody uuid;
            original_type varchar(10);
            actor_role varchar(5);
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

                IF actor_role = 'USER'
                   AND NEW.custody_user_id IS DISTINCT FROM NEW.actor_user_id
                THEN
                    RAISE EXCEPTION
                        'user issue/return custody must match movement actor'
                        USING ERRCODE = '23514';
                END IF;

                IF actor_role = 'ADMIN'
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
    op.execute(
        """
        CREATE TRIGGER trg_movements_validate_custody
        BEFORE INSERT ON movements
        FOR EACH ROW
        EXECUTE FUNCTION validate_movement_custody();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()

    op.execute(
        "LOCK TABLE movements, user_item_custody_balances "
        "IN ACCESS EXCLUSIVE MODE"
    )

    has_history = connection.execute(
        sa.text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM movements
                    WHERE custody_user_id IS NOT NULL
                )
                OR EXISTS (
                    SELECT 1
                    FROM user_item_custody_balances
                )
            """
        )
    ).scalar()

    if has_history:
        raise RuntimeError(
            "custody downgrade refused: custody history or projection exists"
        )

    op.execute(
        "DROP TRIGGER IF EXISTS trg_movements_validate_custody "
        "ON movements"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS validate_movement_custody()"
    )

    op.drop_index(
        op.f("ix_user_item_custody_balances_item_id"),
        table_name="user_item_custody_balances",
    )
    op.drop_table("user_item_custody_balances")

    op.drop_constraint(
        op.f("ck_movements_custody_movement_type"),
        "movements",
        type_="check",
    )
    op.drop_index(
        op.f("ix_movements_custody_user_id"),
        table_name="movements",
    )
    op.drop_constraint(
        op.f("fk_movements_custody_user_id_users"),
        "movements",
        type_="foreignkey",
    )
    op.drop_column("movements", "custody_user_id")
