"""PostgreSQL regressions for the deterministic RBAC migration."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_helpers import alembic

PREVIOUS = "f8a9b0c1d2e3"
HEAD = "a1b2c3d4e5f6"
pytestmark = pytest.mark.asyncio


async def _seed_legacy_users(url: str) -> tuple[str, str]:
    engine = create_async_engine(url)
    async with engine.begin() as db:
        user_id = str(
            await db.scalar(
                text(
                    "INSERT INTO users (id, role, access_status) "
                    "VALUES (gen_random_uuid(), 'USER', 'APPROVED') RETURNING id"
                )
            )
        )
        admin_id = str(
            await db.scalar(
                text(
                    "INSERT INTO users (id, role, access_status) "
                    "VALUES (gen_random_uuid(), 'ADMIN', 'APPROVED') RETURNING id"
                )
            )
        )
    await engine.dispose()
    return user_id, admin_id


async def test_rbac_upgrade_migrates_roles_default_and_constraints(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", PREVIOUS)
    user_id, admin_id = await _seed_legacy_users(url)
    alembic(url, "upgrade", HEAD)

    engine = create_async_engine(url)
    async with engine.begin() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        roles = dict(
            (
                await db.execute(
                    text("SELECT id::text, role FROM users ORDER BY id")
                )
                ).tuples().all()
        )
        assert roles[user_id] == "ENGINEER"
        assert roles[admin_id] == "ADMIN"
        default = await db.scalar(
            text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='users' "
                "AND column_name='role'"
            )
        )
        assert default is not None and "ENGINEER" in default

        savepoint = await db.begin_nested()
        with pytest.raises(IntegrityError):
            await db.execute(
                text(
                    "INSERT INTO users (id, role, access_status) "
                    "VALUES (gen_random_uuid(), 'USER', 'PENDING')"
                )
            )
        await savepoint.rollback()

    await engine.dispose()


async def test_owner_singleton_and_role_audit_constraints(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", HEAD)
    engine = create_async_engine(url)
    async with engine.begin() as db:
        owner_id = await db.scalar(
            text(
                "INSERT INTO users (id, role, access_status) "
                "VALUES (gen_random_uuid(), 'OWNER', 'APPROVED') RETURNING id"
            )
        )
        engineer_id = await db.scalar(
            text(
                "INSERT INTO users (id, role, access_status) "
                "VALUES (gen_random_uuid(), 'ENGINEER', 'APPROVED') RETURNING id"
            )
        )
        await db.execute(
            text(
                "INSERT INTO user_role_events "
                "(id, actor_user_id, target_user_id, before_role, after_role) "
                "VALUES (gen_random_uuid(), :owner, :target, 'ENGINEER', 'MANAGER')"
            ),
            {"owner": owner_id, "target": engineer_id},
        )

    async with engine.begin() as db:
        savepoint = await db.begin_nested()
        with pytest.raises(IntegrityError):
            await db.execute(
                text(
                    "INSERT INTO users (id, role, access_status) "
                    "VALUES (gen_random_uuid(), 'OWNER', 'APPROVED')"
                )
            )
        await savepoint.rollback()

        savepoint = await db.begin_nested()
        with pytest.raises(IntegrityError):
            await db.execute(
                text(
                    "INSERT INTO user_role_events "
                    "(id, actor_user_id, target_user_id, before_role, after_role) "
                    "VALUES (gen_random_uuid(), :owner, :target, 'ENGINEER', 'ENGINEER')"
                ),
                {"owner": owner_id, "target": engineer_id},
            )
        await savepoint.rollback()
    await engine.dispose()


async def test_rbac_safe_downgrade_maps_representable_roles(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", PREVIOUS)
    user_id, admin_id = await _seed_legacy_users(url)
    alembic(url, "upgrade", HEAD)
    alembic(url, "downgrade", PREVIOUS)

    engine = create_async_engine(url)
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == PREVIOUS
        roles = dict(
            (
                await db.execute(text("SELECT id::text, role FROM users ORDER BY id"))
            ).tuples().all()
        )
        assert roles[user_id] == "USER"
        assert roles[admin_id] == "ADMIN"
    await engine.dispose()


@pytest.mark.parametrize("role", ["SENIOR_ENGINEER", "MANAGER", "OWNER"])
async def test_rbac_downgrade_fails_closed_for_unrepresentable_roles(
    migration_database: str,
    role: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", HEAD)
    engine = create_async_engine(url)
    async with engine.begin() as db:
        user_id = await db.scalar(
            text(
                "INSERT INTO users (id, role, access_status) "
                "VALUES (gen_random_uuid(), :role, 'APPROVED') RETURNING id"
            ),
            {"role": role},
        )

    output = alembic(url, "downgrade", PREVIOUS, success=False)
    assert "not representable by USER/ADMIN" in output
    async with engine.connect() as db:
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert await db.scalar(
            text("SELECT role FROM users WHERE id = :id"), {"id": user_id}
        ) == role
    await engine.dispose()


async def test_rbac_downgrade_fails_closed_for_role_audit_history(
    migration_database: str,
) -> None:
    url = migration_database
    alembic(url, "upgrade", HEAD)

    engine = create_async_engine(url)

    async with engine.begin() as db:
        actor_id = await db.scalar(
            text(
                "INSERT INTO users (id, role, access_status) "
                "VALUES (gen_random_uuid(), 'ADMIN', 'APPROVED') "
                "RETURNING id"
            )
        )
        target_id = await db.scalar(
            text(
                "INSERT INTO users (id, role, access_status) "
                "VALUES (gen_random_uuid(), 'ENGINEER', 'APPROVED') "
                "RETURNING id"
            )
        )
        event_id = await db.scalar(
            text(
                "INSERT INTO user_role_events "
                "(id, actor_user_id, target_user_id, "
                "before_role, after_role) "
                "VALUES "
                "(gen_random_uuid(), :actor, :target, "
                "'ENGINEER', 'ADMIN') "
                "RETURNING id"
            ),
            {
                "actor": actor_id,
                "target": target_id,
            },
        )

    output = alembic(
        url,
        "downgrade",
        PREVIOUS,
        success=False,
    )

    assert (
        "user_role_events contains immutable audit history"
        in output
    )

    async with engine.connect() as db:
        assert (
            await db.scalar(
                text(
                    "SELECT version_num "
                    "FROM alembic_version"
                )
            )
            == HEAD
        )

        assert (
            await db.scalar(
                text(
                    "SELECT count(*) "
                    "FROM user_role_events "
                    "WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )
            == 1
        )

        assert (
            await db.scalar(
                text(
                    "SELECT role FROM users "
                    "WHERE id = :target_id"
                ),
                {"target_id": target_id},
            )
            == "ENGINEER"
        )

    await engine.dispose()
