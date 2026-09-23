import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migration_helpers import alembic

pytestmark = pytest.mark.asyncio

PREVIOUS_HEAD = "a9c0d1e2f3a4"
CURRENT_HEAD = "b0c1d2e3f4a5"


async def test_ethernet_patch_cord_catalog_migration(
    migration_database: str,
) -> None:
    alembic(
        migration_database,
        "upgrade",
        PREVIOUS_HEAD,
    )

    engine = create_async_engine(migration_database)

    try:
        async with engine.connect() as db:
            assert await db.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM categories
                    WHERE key = 'ethernet_patch_cord'
                    """
                )
            ) == 0

        alembic(
            migration_database,
            "upgrade",
            CURRENT_HEAD,
        )

        async with engine.connect() as db:
            row = (
                await db.execute(
                    text(
                        """
                        SELECT
                            leaf.display_name,
                            parent.key AS parent_key,
                            parent.display_name AS parent_name
                        FROM categories AS leaf
                        JOIN categories AS parent
                          ON parent.id = leaf.parent_id
                        WHERE leaf.key = 'ethernet_patch_cord'
                        """
                    )
                )
            ).one()

            assert row.display_name == "Ethernet патч-корды"
            assert row.parent_key == "copper_cabling"
            assert row.parent_name == "Медные кабели"

            attributes = (
                await db.execute(
                    text(
                        """
                        SELECT
                            key,
                            label,
                            data_type,
                            unit,
                            required,
                            filter_type
                        FROM category_attributes
                        WHERE category_id = (
                            SELECT id
                            FROM categories
                            WHERE key = 'ethernet_patch_cord'
                        )
                        ORDER BY sort_order, key
                        """
                    )
                )
            ).all()

            assert [
                tuple(attribute)
                for attribute in attributes
            ] == [
                (
                    "cable_category",
                    "Категория",
                    "TEXT",
                    None,
                    True,
                    "EXACT",
                ),
                (
                    "connector_a",
                    "Разъём A",
                    "TEXT",
                    None,
                    True,
                    "EXACT",
                ),
                (
                    "connector_b",
                    "Разъём B",
                    "TEXT",
                    None,
                    True,
                    "EXACT",
                ),
                (
                    "length_m",
                    "Длина",
                    "DECIMAL",
                    "м",
                    True,
                    "RANGE",
                ),
                (
                    "shielding",
                    "Экранирование",
                    "TEXT",
                    None,
                    True,
                    "EXACT",
                ),
                (
                    "color",
                    "Цвет",
                    "TEXT",
                    None,
                    True,
                    "EXACT",
                ),
            ]

            hdd_attributes = (
                await db.execute(
                    text(
                        """
                        SELECT
                            key,
                            label,
                            data_type,
                            unit,
                            required,
                            sort_order
                        FROM category_attributes
                        WHERE category_id = (
                            SELECT id
                            FROM categories
                            WHERE key = 'hdd'
                        )
                        ORDER BY sort_order, key
                        """
                    )
                )
            ).all()

            assert [
                tuple(attribute)
                for attribute in hdd_attributes
            ] == [
                ("form_factor", "Форм-фактор", "TEXT", None, True, 0),
                ("interface", "Интерфейс", "TEXT", None, True, 1),
                ("capacity", "Объём", "TEXT", None, True, 2),
                (
                    "interface_speed",
                    "Скорость интерфейса",
                    "TEXT",
                    None,
                    True,
                    3,
                ),
                (
                    "rpm",
                    "Скорость вращения",
                    "INTEGER",
                    "RPM",
                    True,
                    4,
                ),
                ("type", "Тип", "TEXT", None, True, 5),
            ]

        alembic(
            migration_database,
            "downgrade",
            PREVIOUS_HEAD,
        )

        async with engine.connect() as db:
            assert await db.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM categories
                    WHERE key IN (
                        'ethernet_patch_cord',
                        'copper_cabling'
                    )
                    """
                )
            ) == 0

            assert await db.scalar(
                text(
                    """
                    SELECT count(*)
                    FROM category_attributes
                    WHERE category_id = (
                        SELECT id
                        FROM categories
                        WHERE key = 'hdd'
                    )
                      AND key = 'interface_speed'
                    """
                )
            ) == 0
    finally:
        await engine.dispose()
