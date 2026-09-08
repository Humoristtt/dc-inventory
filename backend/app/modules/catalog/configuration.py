"""Fixed product configuration, derived from inventory.xlsx worksheet columns.

Only migrations change these schemas. No runtime schema construction API exists.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Attribute:
    key: str
    label: str
    required: bool = True
    data_type: str = "TEXT"
    unit: str | None = None
    derived: bool = False


FAMILIES = {
    "transceivers": ("Трансиверы", "SFP, SFP+, SFP28, XFP и QSFP для Ethernet и Fibre Channel."),
    "optics": ("Оптика", "Оптические патч-корды, MPO/LC-кабели и сплиттеры."),
    "network_adapters": ("Сетевые адаптеры", "Сетевые карты Ethernet и адаптеры Fibre Channel."),
    "storage": ("Накопители", "Твердотельные SSD и жёсткие диски HDD."),
    "memory": ("Оперативная память", "Модули серверной оперативной памяти."),
    "pcie": ("PCIe-адаптеры", "Контроллеры и адаптеры расширения PCIe."),
    "power": ("Кабели питания", "Кабели питания для серверов и сетевого оборудования."),
}

TRANSCEIVER_ATTRIBUTES = (
    Attribute("speed", "Скорость"),
    Attribute("wavelength", "Длина волны"),
    Attribute("reach", "Дальность"),
    Attribute("form_factor", "Форм-фактор"),
    Attribute("fiber", "Волокно / среда"),
    Attribute("connector", "Разъём"),
    Attribute("reach_m", "Максимальная дальность", data_type="INTEGER", unit="м", derived=True),
)
NETWORK_ATTRIBUTES = (
    Attribute("interface", "Интерфейс PCIe"),
    Attribute("ports", "Количество портов", data_type="INTEGER"),
    Attribute("speed", "Скорость"),
    Attribute("port_type", "Тип портов"),
    Attribute("application", "Назначение"),
)
DRIVE_ATTRIBUTES = (
    Attribute("form_factor", "Форм-фактор"),
    Attribute("interface", "Интерфейс"),
    Attribute("capacity", "Объём"),
)
LEAVES = {
    "transceiver_ethernet": ("transceivers", "Ethernet", TRANSCEIVER_ATTRIBUTES),
    "transceiver_fc": ("transceivers", "Fibre Channel", TRANSCEIVER_ATTRIBUTES),
    "optical_patch_cord": (
        "optics",
        "Оптические патч-корды",
        (
            Attribute("fiber", "Тип волокна"),
            Attribute("fiber_category", "Категория волокна"),
            Attribute("connector_a", "Разъём A"),
            Attribute("connector_b", "Разъём B"),
            Attribute("length_m", "Длина", data_type="DECIMAL", unit="м"),
            Attribute("construction", "Исполнение"),
            Attribute("color", "Цвет", required=False),
        ),
    ),
    "optical_splitter": (
        "optics",
        "Сплиттеры и делители",
        (
            Attribute("type", "Тип"),
            Attribute("configuration", "Конфигурация"),
            Attribute("fiber", "Волокно"),
            Attribute("wavelength", "Рабочие длины волн"),
            Attribute("connector", "Разъёмы"),
            Attribute("split_ratio", "Деление"),
            Attribute("construction", "Исполнение"),
        ),
    ),
    "network_ethernet": ("network_adapters", "Ethernet", NETWORK_ATTRIBUTES),
    "network_fc": ("network_adapters", "Fibre Channel", NETWORK_ATTRIBUTES),
    "ssd": (
        "storage",
        "SSD",
        (
            *DRIVE_ATTRIBUTES,
            Attribute("interface_speed", "Скорость интерфейса"),
            Attribute("type", "Тип"),
        ),
    ),
    "hdd": (
        "storage",
        "HDD",
        (
            *DRIVE_ATTRIBUTES,
            Attribute("rpm", "Скорость вращения", data_type="INTEGER", unit="RPM"),
            Attribute("type", "Тип"),
        ),
    ),
    "ram": (
        "memory",
        "Оперативная память",
        (
            Attribute("capacity", "Объём"),
            Attribute("type", "Тип"),
            Attribute("speed", "Скорость"),
            Attribute("organization", "Организация"),
            Attribute("ecc", "ECC", data_type="BOOLEAN"),
        ),
    ),
    "pcie_adapter": (
        "pcie",
        "PCIe-адаптеры",
        (
            Attribute("interface", "Интерфейс"),
            Attribute("ports", "Порты"),
            Attribute("application", "Назначение"),
            Attribute("features", "Особенности"),
        ),
    ),
    "power_cable": (
        "power",
        "Кабели питания",
        (
            Attribute("type", "Тип"),
            Attribute("connector_a", "Разъём A"),
            Attribute("connector_b", "Разъём B"),
            Attribute("length_m", "Длина", data_type="DECIMAL", unit="м"),
            Attribute("rating", "Номинал"),
            Attribute("color", "Цвет"),
        ),
    ),
}

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


MANUFACTURED_LEAVES = frozenset(
    {
        "transceiver_ethernet",
        "transceiver_fc",
        "network_ethernet",
        "network_fc",
        "ssd",
        "hdd",
        "ram",
        "pcie_adapter",
    }
)
