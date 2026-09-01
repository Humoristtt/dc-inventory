# Каноническая схема каталога

## Статус документа

Этот документ фиксирует backend/domain contract Stage 5 — Catalog Foundation.

Каталог хранится в PostgreSQL и не синхронизируется из Excel при старте
приложения. Первая версия пяти системных категорий создаётся Alembic-миграцией
`f4a5b6c7d8e9`.

Исходные Excel/CSV-файлы в текущем локальном workspace отсутствовали. Поэтому
структура категорий version-controlled и пригодна для работы, но часть
controlled vocabularies, отмеченная ниже, остаётся предварительной до сверки с
реальной складской номенклатурой.

## Предметные сущности

### Category

`Category` задаёт стабильный тип оборудования и его schema metadata.

Основные поля:

- UUID `id`;
- уникальный machine key `key`;
- `display_name` и optional `description`;
- `default_accounting_mode`;
- `sort_order`;
- `is_system`;
- timestamps.

Бизнес-логика использует `key`, а не локализованный `display_name`.

Системные keys первой версии:

- `sfp`;
- `optics`;
- `power_cable`;
- `nic`;
- `disk`.

Stage 5 не предоставляет API удаления или произвольного редактирования
системных категорий.

### Manufacturer

`Manufacturer` — канонический бренд/производитель.

Поля:

- UUID `id`;
- пользовательское `name`;
- уникальное `normalized_name`;
- timestamps.

Нормализация:

1. trim;
2. схлопывание повторных whitespace;
3. Unicode-aware `casefold()` для comparison identity.

Поэтому `Cisco`, `cisco` и ` Cisco ` конфликтуют как один производитель.
Display name хранится отдельно от comparison value.

Manufacturer не заменяет `Item.manufacturer_part_number`. Производитель у Item
может отсутствовать.

### Item

`Item` — каноническая **каталожная позиция**, а не отдельный физический
экземпляр.

Общие поля:

- UUID `id`;
- обязательная `category_id`;
- optional `manufacturer_id`;
- обязательное `name`;
- optional `model`;
- optional `manufacturer_part_number`;
- optional `internal_code`;
- optional `description`;
- `accounting_mode`;
- `status`;
- optional `comment`;
- optional `datasheet_url`;
- optional `technical_data_source`;
- `archived_at`;
- timestamps.

Для deterministic comparison дополнительно хранятся normalized values имени,
модели, manufacturer part number и internal code.

`internal_code` имеет глобальную case-insensitive uniqueness policy после trim,
whitespace normalization и `casefold()`. Исходное display value сохраняется в
`internal_code`, unique constraint установлен на `normalized_internal_code`.
SQL NULL допускает несколько Item без internal code.

`manufacturer_part_number` не является hard unique. Для него используется
domain-level duplicate candidate check.

### Item и будущий InventoryUnit

`Item` описывает модель/позицию каталога:

- что это за оборудование;
- его общие технические характеристики;
- какой режим учёта применяется.

Будущий `InventoryUnit` будет описывать конкретный физический экземпляр при
SERIAL-учёте. В Stage 5 в Item намеренно не добавлены:

- serial number;
- WWN;
- firmware;
- holder/custody;
- текущая физическая location;
- состояние конкретного экземпляра.

Архивирование или rename Item не меняет его UUID, поэтому будущие исторические
ссылки смогут продолжать разрешаться.

## Structural enums

### AccountingMode

- `QUANTITY`;
- `SERIAL`.

Если mode не передан при создании Item, применяется
`Category.default_accounting_mode`.

После создания `accounting_mode` неизменяем в Stage 5. Это исключает
неоднозначный переход между количественным и серийным учётом перед появлением
inventory ledger.

Defaults:

- `sfp` — `QUANTITY`;
- `optics` — `QUANTITY`;
- `power_cable` — `QUANTITY`;
- `nic` — `SERIAL`;
- `disk` — `SERIAL`.

### ItemStatus

- `ACTIVE`;
- `ARCHIVED`.

DB constraint связывает status и `archived_at`:

- ACTIVE требует `archived_at IS NULL`;
- ARCHIVED требует `archived_at IS NOT NULL`.

### AttributeDataType

- `TEXT`;
- `INTEGER`;
- `DECIMAL`;
- `BOOLEAN`;
- `ENUM`.

### FilterType

- `NONE`;
- `EXACT`;
- `RANGE`.

Stage 5 сохраняет filter metadata, но не реализует faceted filtering.

## CategoryAttribute metadata

Каждый `CategoryAttribute` принадлежит одной Category и содержит:

- стабильный `key`;
- `label`;
- `data_type`;
- optional canonical `unit`;
- `required`;
- `filterable`;
- `searchable`;
- `card_visible`;
- `detail_visible`;
- `table_visible`;
- `excel_visible`;
- `sort_order`;
- `filter_type`;
- optional JSONB `allowed_values`;
- optional JSONB `validation_metadata`;
- `is_system`;
- timestamps.

Уникальность: `(category_id, key)`.

`allowed_values`:

- разрешён только для `ENUM`;
- представляет непустой JSON array;
- элементы являются canonical case-sensitive strings;
- соответствие supplied value списку проверяется backend.

`validation_metadata` представляет JSON object. Текущий versioned contract:

- `min` / `max` для INTEGER и DECIMAL;
- `max_length` для TEXT.

Новые правила metadata должны добавляться вместе с backend support и новой
миграцией.

## Typed ItemAttributeValue

Технические характеристики не хранятся единым uncontrolled JSON document.

`ItemAttributeValue` содержит:

- UUID `id`;
- `item_id`;
- `category_attribute_id`;
- redundant `category_id` для DB-level cross-category integrity;
- `text_value`;
- `integer_value` как signed 64-bit integer;
- `decimal_value` как `NUMERIC(30, 10)`;
- `boolean_value`;
- `enum_value`.

Уникальность: `(item_id, category_attribute_id)`.

PostgreSQL constraint
`num_nonnulls(text_value, integer_value, decimal_value, boolean_value,
enum_value) = 1` требует ровно одно typed value.

Mapping:

- TEXT -> `text_value`;
- INTEGER -> `integer_value`;
- DECIMAL -> `decimal_value`;
- BOOLEAN -> `boolean_value`;
- ENUM -> `enum_value`.

Соответствие populated column значению `CategoryAttribute.data_type` проверяет
service boundary. Cross-category assignment дополнительно запрещён двумя
composite foreign keys:

- `(item_id, category_id) -> items(id, category_id)`;
- `(category_attribute_id, category_id) ->
  category_attributes(id, category_id)`.

Таким образом, Item не может получить attribute другой Category ни через
штатный service, ни прямой неконсистентной DB insert.

## Backend validation

Create Item и полная замена attributes выполняют metadata-driven validation:

1. Category должна существовать.
2. Каждый supplied key должен существовать в schema этой Category.
3. Все required attributes должны быть переданы.
4. Required TEXT/ENUM не принимают whitespace-only value.
5. Тип должен совпадать с metadata.
6. ENUM value должен входить в `allowed_values`.
7. Python bool не принимается как INTEGER.
8. INTEGER должен помещаться в signed 64-bit range.
9. DECIMAL не принимает binary float.
10. DECIMAL принимается как exact decimal string, integer либо `Decimal` во
    внутренних Python-вызовах.
11. DECIMAL ограничен precision 30 и scale 10 без скрытого округления.
12. `min`, `max` и `max_length` применяются при наличии.
13. Optional blank TEXT/ENUM нормализуется как отсутствующее значение.

В JSON API exact decimal рекомендуется передавать строкой, например `"2.5"`.
Ответ также сериализует Decimal как строку, сохраняя точность.

Create Item и его attribute rows фиксируются одной транзакцией. Ошибка
валидации или persistence не оставляет частично созданный Item.

## Канонические единицы

В БД хранятся machine values:

- `speed_mbps`, `port_speed_mbps`, `interface_speed_mbps` — Mbps;
- `reach_m` — metres;
- `length_m` — metres как Decimal;
- `tx_wavelength_nm`, `rx_wavelength_nm` — nanometres как Decimal;
- `rated_current_a` — amperes как Decimal;
- `rated_voltage_v` — volts;
- `capacity_bytes` — bytes как signed 64-bit integer;
- `rpm` — revolutions per minute.

Presentation strings вроде `10G`, `10 km` и `1.92 TB` будут формироваться
будущим UI/export layer.

## Initial system schemas

### SFP / optical transceivers

Default accounting: `QUANTITY`.

| Key | Type | Required | Unit / controlled values |
|---|---|---:|---|
| `form_factor` | ENUM | no | SFP, SFP+, SFP28, QSFP+, QSFP28, QSFP56, QSFP-DD |
| `speed_mbps` | INTEGER | yes | Mbps, min 1 |
| `medium` | ENUM | no | SMF, MMF, Copper, DAC, AOC |
| `reach_class` | ENUM | no | SR, LR, ER, ZR, BiDi, CWDM, DWDM |
| `reach_m` | INTEGER | no | m, min 0 |
| `connector` | ENUM | no | LC Duplex, LC Simplex, MPO/MTP, RJ45 |
| `tx_wavelength_nm` | DECIMAL | no | nm, min 0 |
| `rx_wavelength_nm` | DECIMAL | no | nm, min 0 |
| `dom_ddm` | BOOLEAN | no | — |
| `vendor_compatibility` | TEXT | no | max length 2000 |

Списки form factor, medium, reach class и connector являются первой
расширяемой версией, а не заявлением о глобальной полноте.

### Optical cabling

Default accounting: `QUANTITY`.

| Key | Type | Required | Unit / controlled values |
|---|---|---:|---|
| `product_type` | TEXT | yes | provisional text |
| `fiber_mode` | ENUM | yes | SM, MM |
| `fiber_standard` | ENUM | no | OS2, OM2, OM3, OM4, OM5 |
| `connector_a` | TEXT | yes | provisional text |
| `polish_a` | ENUM | no | UPC, APC |
| `connector_b` | TEXT | no | provisional text |
| `polish_b` | ENUM | no | UPC, APC |
| `fiber_count` | INTEGER | no | min 1 |
| `length_m` | DECIMAL | yes | m, min 0 |
| `color` | TEXT | no | provisional text |
| `polarity` | TEXT | no | provisional text |

Connector и polish разделены: `LC/APC` не является одним полем.

`product_type`, connector, color и polarity остаются TEXT до сверки реальных
значений. Они могут быть переведены в versioned ENUM metadata новой миграцией,
если источник подтвердит устойчивый vocabulary.

### Power cables

Default accounting: `QUANTITY`.

| Key | Type | Required | Unit / notes |
|---|---|---:|---|
| `connector_a` | TEXT | yes | provisional vocabulary |
| `connector_b` | TEXT | yes | provisional vocabulary |
| `length_m` | DECIMAL | yes | m, min 0 |
| `color` | TEXT | no | provisional vocabulary |
| `rated_current_a` | DECIMAL | no | A, min 0 |
| `rated_voltage_v` | INTEGER | no | V, min 0 |

Stage 5 не реализует global search по строке `C13 C14`.

### Network interface cards

Default accounting: `SERIAL`.

| Key | Type | Required | Unit / controlled values |
|---|---|---:|---|
| `port_count` | INTEGER | yes | min 1 |
| `port_speed_mbps` | INTEGER | yes | Mbps, min 1 |
| `media_type` | ENUM | no | RJ45, SFP+, SFP28, QSFP+, QSFP28 |
| `pcie_generation` | TEXT | no | provisional text |
| `pcie_lanes` | INTEGER | no | min 1 |
| `protocol` | ENUM | no | Ethernet, Fibre Channel, InfiniBand |
| `bracket` | ENUM | no | full_profile, low_profile, unknown |
| `sriov` | BOOLEAN | no | — |
| `rdma_roce` | BOOLEAN | no | — |

SERIAL default не создаёт физические NIC units в Stage 5.

### Disks / drives

Default accounting: `SERIAL`.

| Key | Type | Required | Unit / controlled values |
|---|---|---:|---|
| `drive_type` | ENUM | yes | HDD, SSD, NVMe |
| `capacity_bytes` | INTEGER | yes | bytes, min 1 |
| `form_factor` | ENUM | no | 2.5, 3.5, M.2, U.2, U.3 |
| `interface` | ENUM | yes | SATA, SAS, NVMe |
| `interface_speed_mbps` | INTEGER | no | Mbps, min 1 |
| `rpm` | INTEGER | no | rpm, min 1 |
| `sector_format` | TEXT | no | provisional text |
| `endurance` | TEXT | no | provisional text |

Serial number, WWN, firmware, holder, location и состояние физического диска
относятся к будущему InventoryUnit.

## Duplicate detection

Duplicate check является read-only domain operation и не создаёт, не меняет и
не удаляет Item.

Strong MPN signal:

- та же Category;
- тот же Manufacturer, включая вариант «оба неизвестны»;
- одинаковый normalized manufacturer part number.

MPN normalization:

- trim;
- whitespace normalization;
- casefold;
- punctuation сохраняется.

Когда MPN отсутствует:

- та же Category;
- тот же Manufacturer, включая «оба неизвестны»;
- точное совпадение normalized name;
- точное совпадение normalized model, включая «оба отсутствуют».

Fuzzy/Levenshtein/AI matching не используется. Candidate result информирует
ADMIN, но не запрещает создать неоднозначную легитимную позицию.

## Archive/unarchive

Обычного DELETE Item endpoint нет.

- archive: `ACTIVE -> ARCHIVED`, устанавливает `archived_at`;
- повторный archive: idempotent no-op, исходный `archived_at` сохраняется;
- unarchive: `ARCHIVED -> ACTIVE`, очищает `archived_at`;
- повторный unarchive: idempotent no-op;
- archived Item остаётся доступен по ID.

Обычный list использует `status=ACTIVE`. Архив доступен явным
`status=ARCHIVED`.

## API contract

### Approved read API

Требует существующую authorization boundary `Approved`:

- `GET /api/catalog/categories`;
- `GET /api/catalog/categories/{category_key}`;
- `GET /api/catalog/manufacturers`;
- `GET /api/catalog/items`;
- `GET /api/catalog/items/{item_id}`.

PENDING, REJECTED и BLOCKED получают 403; отсутствие валидной session — 401.
APPROVED USER и APPROVED ADMIN могут читать.

Category detail возвращает frontend-friendly metadata. Item response возвращает
единый `attributes` object по key/value и не раскрывает пять nullable EAV
columns.

Item list:

- deterministic order по normalized name и UUID;
- default limit 50, max 100;
- offset pagination;
- optional Category filter;
- default status ACTIVE.

Manufacturer list использует limit/offset pagination.

### Admin mutation API

Требует существующую boundary `Admin`, то есть `APPROVED + ADMIN`:

- `POST /api/admin/catalog/manufacturers`;
- `POST /api/admin/catalog/items`;
- `PATCH /api/admin/catalog/items/{item_id}`;
- `POST /api/admin/catalog/items/{item_id}/archive`;
- `POST /api/admin/catalog/items/{item_id}/unarchive`;
- `POST /api/admin/catalog/items/check-duplicates`.

APPROVED USER получает 403.

Ошибки domain validation имеют стабильный `detail`:

```json
{
  "code": "category_immutable",
  "message": "item category cannot be changed"
}
```

Raw SQL/IntegrityError text клиенту не возвращается.

## PATCH semantics

PATCH меняет только переданные scalar fields.

- `category_key` неизменяем после создания;
- `accounting_mode` неизменяем после создания;
- status меняется только archive/unarchive operations;
- explicit NULL очищает nullable scalar field;
- NULL для обязательного `name` запрещён;
- если `attributes` отсутствует, текущий set сохраняется;
- если `attributes` присутствует, он **полностью заменяет** set атрибутов Item;
- `attributes: null` запрещён;
- replacement повторно проверяет все required fields.

Scalar changes и attribute replacement входят в одну API-owned transaction.

## Versioning strategy

Миграция `f4a5b6c7d8e9`:

1. создаёт catalog tables, constraints, FKs и indexes;
2. вставляет пять Category со стабильными UUID;
3. вставляет system CategoryAttribute со стабильными UUID;
4. не импортирует runtime constants;
5. не запускается автоматически как schema repair на старте приложения.

Будущие изменения system schema выполняются только новыми Alembic revisions.
Старая migration остаётся исторически неизменной.

## Database integrity and delete policy

DB-level invariants:

- unique Category key;
- unique Manufacturer normalized name;
- unique normalized internal code;
- unique `(category_id, attribute key)`;
- unique `(item_id, category_attribute_id)`;
- exactly one typed value;
- cross-category composite FKs;
- structural enum checks;
- archive state check;
- JSONB shape checks.

Delete policy:

- Category <- Item: `RESTRICT`;
- Category <- CategoryAttribute: `RESTRICT`;
- Manufacturer <- Item: `RESTRICT`;
- CategoryAttribute <- ItemAttributeValue: `RESTRICT`;
- Item <- ItemAttributeValue: `CASCADE`.

Последний cascade предназначен для migration/test/internal teardown. Публичного
hard-delete Item API нет.

Indexes ограничены текущими Stage 5 query patterns: category/status listing,
manufacturer FK, duplicate MPN, duplicate normalized name/model и FK/unique
lookups. Индексы для будущих faceted queries откладываются до появления
реальных запросов.

## Deliberately deferred

Stage 5 не реализует:

- Movement/MovementLine;
- StockBalance и quantity;
- InventoryUnit/serial lifecycle;
- location, holder и custody;
- receiving/issuing/return/transfer/write-off;
- global search и faceted filters;
- media;
- Excel import/export;
- frontend catalog UI;
- Redis, Elasticsearch, queues или новые services.

## Source inventory reconciliation

В текущем workspace не найдено Excel/CSV source inventory, поэтому фактическая
сверка не выполнена.

Остаются provisional:

- optics `product_type`;
- optics/power connector vocabularies;
- optics/power color vocabulary;
- optics polarity;
- NIC PCIe generation notation;
- disk sector format/endurance notation;
- полнота перечислений SFP connector/reach/form factor;
- дополнительные реальные category variants.

Следующий Stage 5 шаг — предоставить реальные source files, сопоставить source
values с canonical keys/units и оформить source-to-canonical mapping новой
документированной migration при необходимости. Excel при этом не становится
runtime source of truth.
