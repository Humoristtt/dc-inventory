"""Add descriptions for fixed leaf catalog categories.

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEAF_DESCRIPTIONS = {
    "transceiver_ethernet": "Трансиверы SFP, SFP+, SFP28, XFP и QSFP для Ethernet-сетей.",
    "transceiver_fc": "Оптические трансиверы для Fibre Channel SAN.",
    "optical_patch_cord": (
        "Одномодовые и многомодовые оптические патч-корды "
        "с различными типами разъёмов."
    ),
    "optical_splitter": "Оптические сплиттеры и делители для распределения оптического сигнала.",
    "network_ethernet": "Сетевые Ethernet-адаптеры и многопортовые NIC.",
    "network_fc": "HBA-адаптеры для подключения серверов к Fibre Channel SAN.",
    "ssd": "Твердотельные накопители SATA, SAS и NVMe.",
    "hdd": "Серверные жёсткие диски SAS и SATA.",
    "ram": "Серверные модули оперативной памяти разных объёмов и поколений.",
    "pcie_adapter": "Контроллеры и специализированные платы расширения PCIe.",
    "power_cable": "Кабели питания для серверного и сетевого оборудования.",
}


def upgrade() -> None:
    connection = op.get_bind()

    for key, description in LEAF_DESCRIPTIONS.items():
        result = connection.execute(
            sa.text(
                """
                UPDATE categories
                SET description = :description
                WHERE key = :key
                  AND is_system = true
                  AND parent_id IS NOT NULL
                """
            ),
            {
                "key": key,
                "description": description,
            },
        )

        if result.rowcount != 1:
            raise RuntimeError(
                f"expected exactly one system leaf category for {key!r}; "
                f"updated {result.rowcount}"
            )


def downgrade() -> None:
    connection = op.get_bind()

    for key in LEAF_DESCRIPTIONS:
        result = connection.execute(
            sa.text(
                """
                UPDATE categories
                SET description = NULL
                WHERE key = :key
                  AND is_system = true
                  AND parent_id IS NOT NULL
                """
            ),
            {"key": key},
        )

        if result.rowcount != 1:
            raise RuntimeError(
                f"expected exactly one system leaf category for {key!r}; "
                f"updated {result.rowcount}"
            )
