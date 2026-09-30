# Каталог

Catalog хранит номенклатуру и техническую identity позиции. Количество и движения находятся в Warehouse domain.

## 1. Модель

```text
Category (family)
   │
   └── Category (leaf)
           │
           ├── CategoryAttribute
           │
           └── Item
                 │
                 ├── Manufacturer?
                 └── ItemAttributeValue*
```

Item может принадлежать только leaf-category.

## 2. Фиксированная taxonomy

Runtime API не создаёт новые схемы категорий. Configuration меняется кодом + migrations.

Families: `transceivers`, `optics`, `copper_cabling`, `network_adapters`, `storage`, `memory`, `pcie`, `power`.

Leaves:

- `transceiver_ethernet`;
- `transceiver_fc`;
- `optical_patch_cord`;
- `optical_splitter`;
- `ethernet_patch_cord`;
- `network_ethernet`;
- `network_fc`;
- `ssd`;
- `hdd`;
- `ram`;
- `pcie_adapter`;
- `power_cable`.

Manufactured leaves требуют manufacturer/model согласно текущей configuration policy.

## 3. Типы attributes

Поддерживаются `TEXT`, `INTEGER`, `DECIMAL`, `BOOLEAN`, `ENUM`.

`ItemAttributeValue` хранит typed value в отдельной колонке. Для одного attribute должна быть заполнена корректная колонка, согласованная с `CategoryAttribute.data_type`.

Metadata attribute задаёт required, unit, filterable, searchable, card/detail/table/excel visibility, sort order, filter type, allowed values и validation metadata.

## 4. Технические поля основных leaf

### Трансиверы

speed, wavelength, reach, form_factor, fiber, connector и derived `reach_m`.

### Оптический патч-корд

fiber, fiber_category, connector_a, connector_b, length_m, construction, optional color.

### Ethernet patch cord

cable_category, connector_a/b, length_m, shielding, color.

### Network adapter

interface, ports, speed, port_type, application.

### SSD/HDD

Общие: form_factor, interface, capacity. SSD: interface_speed, type. HDD: interface_speed, rpm, type.

### RAM

capacity, type, speed, organization, ecc.

### PCIe adapter

interface, ports, application, features.

### Power cable

type, connector_a/b, length_m, rating, color.

## 5. Identity

Item имеет `name`, `normalized_name`, optional `model`, `normalized_model`, `identity_signature`.

Identity строится из canonical item fields и identity-relevant EAV values. Нормализация согласована между Python и PostgreSQL. Decimal representation канонизируется до вычисления signature.

DB functions/triggers проверяют, что normalized fields соответствуют source fields, signature соответствует фактическим Item/EAV, а identity нельзя изменить обходом service layer.

`identity_signature` unique.

## 6. Create/update

Application validation:

1. проверяет leaf;
2. проверяет manufactured policy;
3. проверяет manufacturer;
4. проверяет required attributes;
5. нормализует типы;
6. вычисляет technical identity;
7. пишет Item и attributes.

DB deferred triggers повторно проверяют completeness/identity до commit.

## 7. Status и delete

Item status: `ACTIVE` или `ARCHIVED`.

Archived item остаётся исторически доступным, но не должен использоваться для новых операций, где требуется active identity.

Physical delete разрешён только через `catalog.delete_unused` и только если database references позволяют считать позицию неиспользованной.

## 8. Read API и query model

Catalog list поддерживает query string, category, manufacturer, availability, attribute filters, sort/order и pagination.

Sorts: name, relevance, manufacturer, available, total, speed.

Availability: ANY, IN_STOCK, OUT_OF_STOCK.

Query builder формирует bounded SQL plan и отдельные facet queries. Query-count/scalability regressions выполняются на PostgreSQL.

## 9. Связь с Warehouse

Catalog не хранит editable stock field. Остаток присоединяется из Warehouse projection.

Удаление/архивирование Item учитывает warehouse/procurement references.

## 10. Связь с Procurement

Existing procurement line хранит Catalog Item.

Proposed line хранит immutable display snapshot и `expected_identity_signature`. При binding фактический Item обязан иметь совпадающую signature.

Create-and-bind создаёт Item и binding в одной transaction и дополнительно требует `catalog.manage`.

## 11. Readiness contract

Readiness включает Catalog critical DB objects:

- hierarchy/leaf triggers;
- required attributes triggers;
- typed-value trigger;
- identity triggers;
- identity functions;
- Unicode collation.

Удаление/disable одного из критичных объектов делает readiness fail-closed.
