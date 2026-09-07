# Catalog Schema V2

Каноническая схема каталога Warehouse Domain V2.

## Category

Категории задаются приложением и имеют stable machine key и Russian display name.

Иерархия:

- transceivers
  - transceiver_ethernet
  - transceiver_fibre_channel
- optics
  - optical_patch_cords
  - optical_splitters
- network_adapters
  - network_adapter_ethernet
  - network_adapter_fibre_channel
- storage
  - ssd
  - hdd
- memory
- pcie_adapters
- power_cables

Item может принадлежать только leaf category.

long_range не является category. Это derived scope по нормализованной дальности.

## Item

Item представляет номенклатурную позицию, а не физический экземпляр.

Базовые свойства:

- id;
- leaf category key;
- name;
- normalized name;
- optional manufacturer;
- optional model;
- status ACTIVE / ARCHIVED;
- category-specific technical attributes.

Warehouse V2 не использует accounting mode и physical-unit lifecycle.

## Identity

Identity определяется устойчивыми техническими признаками соответствующей
leaf category.

Patch-cord color становится identity-defining только когда значение заполнено.

## Трансиверы

Признаки по применимости:

- manufacturer;
- model;
- speed;
- wavelength;
- reach;
- form factor;
- fiber;
- connector.

Landing copy:

SFP, SFP+, SFP28, XFP и QSFP для Ethernet и Fibre Channel.

Дальние определяются из нормализованного reach_m >= 2000.

## Оптика

Landing copy:

Оптические патч-корды, MPO/LC-кабели и сплиттеры.

Patch-cord признаки по применимости:

- fiber type;
- category/grade;
- connector A;
- connector B;
- length;
- construction;
- optional color.

## Накопители

SSD и HDD являются разными leaf categories независимо от исходного sheet name.

Технические признаки по применимости:

- manufacturer;
- model;
- form factor;
- interface;
- capacity;
- interface speed;
- class.

## Dynamic facets

Facet API вычисляется внутри текущего scoped universe.

После применения category/search/derived scope:

- backend возвращает допустимые values;
- значения с нулевым count не показываются;
- dimension с единственным distinct value скрывается.

Frontend использует известные leaf schemas, а не произвольную runtime category
schema.

## Inventory relation

Item не содержит текущий остаток.

Остаток хранится warehouse projection:

Item × StorageLocation → quantity

Archived Item остаётся доступным для истории и разрешённых операций завершения
существующего остатка.
