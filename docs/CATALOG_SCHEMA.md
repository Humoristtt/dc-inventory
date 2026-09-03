# Каноническая схема каталога

## Статус документа

Этот документ фиксирует backend/domain contract Stage 5 — Catalog Foundation и
Stage 7 — Catalog Read API / Search / Filters.

Каталог хранится в PostgreSQL и не синхронизируется из Excel при старте
приложения. Первая версия пяти системных категорий создаётся Alembic-миграцией
`f4a5b6c7d8e9`; source-backed refinement создаётся следующей миграцией
`a6b7c8d9e0f1`.

Три локальных reference workbook сверены с contract. Они являются примерами
для проектирования каталога, а не авторитетной inventory database или import
source. Существующие количества/остатки не импортируются; фактический stock
проверяется владельцем вручную при вводе оборудования. Подробное сопоставление
зафиксировано в `docs/CATALOG_SOURCE_REFERENCE.md`.

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

Текущие system keys:

- `sfp`;
- `optics`;
- `copper_network_cable`;
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

Non-null `datasheet_url` проходит URL parsing и допускает только валидную
`http`/`https` semantics; arbitrary schemes вроде `javascript:`/`ftp:` и
невалидные link strings отклоняются до persistence.

Для deterministic comparison дополнительно хранятся normalized values имени,
модели, manufacturer part number и internal code.

`internal_code` имеет глобальную case-insensitive uniqueness policy после trim,
whitespace normalization и `casefold()`. Исходное display value сохраняется в
`internal_code`, unique constraint установлен на `normalized_internal_code`.
SQL NULL допускает несколько Item без internal code.

`manufacturer_part_number` не является hard unique. Для него используется
domain-level duplicate candidate check.

### Item и физический InventoryUnit Stage 6

`Item` описывает модель/позицию каталога:

- что это за оборудование;
- его общие технические характеристики;
- какой режим учёта применяется.

Stage 5 намеренно исключил physical inventory из catalog и не добавлял в Item:

- serial number;
- WWN;
- firmware;
- holder/custody;
- текущая физическая location;
- состояние конкретного экземпляра.

Stage 6 теперь реализует конкретный SERIAL-экземпляр как `InventoryUnit`, а
quantity/current positions и canonical movement journal — в отдельном warehouse
domain, описанном `docs/WAREHOUSE_DOMAIN.md`. Архивирование или rename Item не
меняет UUID и не переписывает historical/current inventory references.

Archived Item не принимает новый receipt и не может быть newly issued, но
существующий stock не блокируется: warehouse policy разрешает return, transfer,
write-off и допустимый reversal. Эта policy находится в inventory module;
catalog service не импортирует warehouse models.

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
- `copper_network_cable` — `QUANTITY`;
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
- `max_length` для TEXT;
- `preserve_whitespace` для TEXT — optional boolean, default `false`:
  - `false` или отсутствие ключа нормализует whitespace до одиночных пробелов;
  - `true` удаляет только outer whitespace и сохраняет внутренние пробелы,
    переводы строк и исходное форматирование текста.

`preserve_whitespace` не меняет правило для blank values: whitespace-only TEXT
по-прежнему считается отсутствующим значением, а required поле отклоняется.
Небулево значение `preserve_whitespace` является некорректной metadata.

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
11. DECIMAL ограничен storage contract `NUMERIC(30,10)`: не более 20 цифр в
    целой и 10 цифр в дробной части, без скрытого округления.
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
- `conductor_cross_section_mm2` — square millimetres (`mm2`);
- `capacity_bytes` — bytes как signed 64-bit integer;
- `rpm` — revolutions per minute.

Presentation strings вроде `10G`, `10 km` и `1.92 TB` будут формироваться
будущим UI/export layer.

## Versioned system schemas

### SFP / optical transceivers

Default accounting: `QUANTITY`.

| Key | Type | Required | Unit / controlled values |
|---|---|---:|---|
| `form_factor` | ENUM | no | SFP, SFP+, SFP28, XFP, QSFP+, QSFP28, QSFP56, QSFP-DD |
| `speed_profile` | TEXT | no | exact source-facing speed notation, max length 255 |
| `speed_mbps` | INTEGER | yes | Mbps, min 1 |
| `medium` | ENUM | no | SMF, MMF, Copper, DAC, AOC |
| `reach_class` | ENUM | no | SR, LR, ER, ZR, BiDi, CWDM, DWDM |
| `reach_profile` | TEXT | no | exact/conditional source-facing reach, max length 2000 |
| `reach_m` | INTEGER | no | m, min 0 |
| `connector` | ENUM | no | LC Duplex, LC Simplex, SC Simplex, MPO, MPO/PC, MPO/MTP, RJ45 |
| `wavelength_profile` | TEXT | no | exact source-facing wavelength notation, max length 255 |
| `nominal_wavelength_nm` | DECIMAL | no | nm, min 0 |
| `tx_wavelength_nm` | DECIMAL | no | nm, min 0 |
| `rx_wavelength_nm` | DECIMAL | no | nm, min 0 |
| `dom_ddm` | BOOLEAN | no | — |
| `vendor_compatibility` | TEXT | no | max length 2000 |

Списки form factor, medium, reach class и connector являются расширяемой
versioned metadata, а не заявлением о глобальной полноте. Exact profile fields
сохраняют source text; metadata `preserve_whitespace` сохраняет внутренние
переносы строк после outer trim.

Для multi-rate `speed_profile` `speed_mbps` означает максимальную явно
перечисленную line rate, используемую только для filter/sort: например,
`4/8/16G FC -> 16000`, `8/16/32G FC -> 32000`, `10/25 Гбит/с -> 25000`.
`reach_m` аналогично может содержать только максимальную явно указанную
дистанцию, но условный `reach_profile` обязателен для lossless presentation.
`nominal_wavelength_nm` заполняется только при одной однозначной номинальной
длине волны. Multi-channel profile не сворачивается к произвольному scalar;
`tx_wavelength_nm`/`rx_wavelength_nm` используются только когда source явно
различает TX и RX. `reach_class` и Ethernet/FC protocol по model не выводятся.

Для текущего authoritative SFP contract backend проверяет согласованность
lossless profile и scalar без эвристического разбора текста. Известные
`speed_profile`, `reach_profile` и `wavelength_profile` сопоставляются с
явно зафиксированным ожидаемым scalar. Если profile и scalar переданы вместе,
противоречие отклоняется. Неизвестный profile вместе со scalar также
отклоняется как непроверяемая комбинация; новый authoritative profile должен
быть добавлен в contract явно. Optional reach/wavelength profile без scalar
может храниться losslessly. Multi-channel wavelength profile не допускает
произвольный `nominal_wavelength_nm`.

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
| `conductor_count` | INTEGER | no | min 1 |
| `conductor_cross_section_mm2` | DECIMAL | no | mm2, min 0 |

Stage 5 не реализует global search по строке `C13 C14`.

Два conductor attributes добавлены после reference review повторяющихся
product specifications вида `3×... mm²`. Они optional: отсутствие маркировки
не должно превращаться в выдуманное значение.

### Copper network cables

Default accounting: `QUANTITY`.

| Key | Type | Required | Unit / notes |
|---|---|---:|---|
| `connector_a` | TEXT | yes | provisional canonical text |
| `connector_b` | TEXT | yes | provisional canonical text |
| `length_m` | DECIMAL | yes | m, min 0 |
| `cable_category` | TEXT | yes | e.g. observed Cat notation; not a closed ENUM |
| `shielding` | TEXT | no | provisional vocabulary |

Категория отделяет медные сетевые patch cords от fiber-specific `optics` и
электрических `power_cable`. Connector/category/shielding остаются TEXT:
reference подтверждает стабильные field semantics, но не полный vocabulary.

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

Serial number, WWN, holder, location и состояние физического диска относятся к
Stage 6 `InventoryUnit`; firmware пока не входит в implemented warehouse unit
contract.

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
- `GET /api/catalog/items/facets`;
- `GET /api/catalog/items/{item_id}`.

PENDING, REJECTED и BLOCKED получают 403; отсутствие валидной session — 401.
APPROVED USER и APPROVED ADMIN могут читать.

Category detail возвращает frontend-friendly metadata. Item response возвращает
единый `attributes` object по key/value и не раскрывает пять nullable EAV
columns.

Manufacturer list:

- deterministic order по `normalized_name` и UUID;
- default limit 100, max 200;
- offset pagination;
- optional `q`, максимум 255 characters;
- `q` проходит ту же comparison-normalization, что и canonical manufacturer
  name, и выполняет contains-search по `normalized_name`;
- frontend не считает первую страницу исчерпывающим списком: форма позиции
  использует bounded pages по 50 записей, server-side search и явную загрузку
  следующих страниц.

Item list:

- deterministic order по normalized name и UUID по умолчанию;
- default limit 50, max 100;
- offset pagination;
- optional Category filter;
- default status ACTIVE.

#### Stage 7 item query

`GET /api/catalog/items` принимает:

- optional `q`, максимум 200 characters;
- optional `category` key и `status=ACTIVE|ARCHIVED`;
- repeated `manufacturer_id=<uuid>` и `location_id=<uuid>`;
- `availability=ANY|IN_STOCK|OUT_OF_STOCK`, default `ANY`;
- `sort=name|manufacturer|available|total`, default `name`;
- `order=asc|desc`, default `asc`;
- repeated `filter=<attribute_key>:<operator>:<value>`;
- `limit=1..100`, default 50, и `offset>=0`.

Whitespace-only `q` не добавляет search predicate. Иначе outer whitespace
удаляется, repeated whitespace схлопывается, строка делится на tokens. Между
tokens действует AND, внутри одного token — OR по searchable domain Item. Common
fields: name, model, manufacturer part number, internal code и Manufacturer
name. Description, comment, datasheet URL и technical source не searchable.
User `%` и `_` экранируются как literal symbols и не становятся LIKE wildcard.

Searchable EAV определяется только `CategoryAttribute.searchable`. TEXT/ENUM
используют case-insensitive contains; INTEGER/DECIMAL участвуют только при safe
typed equality; BOOLEAN понимает только explicit `true`/`false`. Engineering
unit conversion (`10G`, `1.92TB`, `10km`) не выполняется. Token может совпасть с
другим field/attribute, чем соседний token: поэтому `C13 C14` может совпасть с
двумя разными searchable connector attributes.

InventoryUnit serial и WWN ищутся по existing normalized identity semantics.
Parent Item возвращается один раз независимо от числа matching units. Identity
видима для STORED, ISSUED, WRITTEN_OFF и VOIDED units; состояние ограничивает
availability totals, но не historical identity search.

Attribute filters требуют `category`. Expression делится только по первым двум
`:`. Metadata выбирается по key и обязана иметь `filterable=true`. EXACT
разрешает `eq`; numeric RANGE metadata разрешает `eq`, `gte`, `lte`, чтобы одна
versioned engineering characteristic поддерживала exact и bounds requests.
Repeated `eq` одного key объединяются OR, разные keys — AND. `gte` и `lte`
одного key образуют inclusive range; duplicate boundary одного направления —
422, а не last-one-wins. TEXT equality нормализует whitespace и игнорирует
case; ENUM принимает только canonical `allowed_values`; INTEGER — signed BIGINT
без bool coercion; DECIMAL — exact NUMERIC(30,10); BOOLEAN — только
`true`/`false`.

Repeated manufacturer/location values имеют OR внутри facet и AND с другими
dimensions. Location совпадает только с positive QUANTITY StockBalance в этой
Location либо STORED SERIAL unit. Archived Location с legitimate current stock
не скрывается. Availability основана только на warehouse stock:

- QUANTITY available = sum Location balances, custody = sum holder balances;
- SERIAL available = STORED count, custody = ISSUED count;
- WRITTEN_OFF/VOIDED дают zero current count;
- total = available + custody;
- IN_STOCK означает available > 0, OUT_OF_STOCK — available = 0.

Каждая list entry дополнительно возвращает:

```json
{
  "inventory": {
    "available_count": 8,
    "custody_count": 2,
    "total_count": 10
  }
}
```

Item detail contract не получает эту list-specific projection. Counts не
persist-ятся в Item и загружаются set-wise вместе со страницей.

Sorting всегда имеет tie-breakers. `name`: normalized item name, Item UUID;
`manufacturer`: normalized manufacturer name, normalized item name, Item UUID,
при этом NULL manufacturer всегда last; `available`/`total`: соответствующий
count, normalized item name, Item UUID. `order` применяется ко всем ключам;
pagination идёт по unique Item rows. `total` считается после всех predicates и
до limit/offset.

#### Stage 7 facets

`GET /api/catalog/items/facets` имеет ту же Approved boundary и принимает тот же
query context (`q`, `category`, `status`, repeated manufacturer/location,
availability, repeated filter), но не pagination/sorting.

Без Category response содержит category, manufacturer, availability и location.
С Category category facet убирается и metadata-driven facets добавляются для
каждого `filterable=true` CategoryAttribute. Exact facet сообщает key, label,
data type, unit/filter type и non-zero values/counts. Manufacturer содержит UUID
и display name; Location — UUID, code и name. ENUM идёт в metadata order,
BOOLEAN в deterministic false/true order, TEXT — в normalized display order.
RANGE не создаёт buckets: возвращает real `min`/`max`; empty dataset возвращает
оба bounds как null, без fabricated `0..0`. Decimal сериализуется точно.

Каждый facet self-excluding: применяются все active predicates кроме predicate
этого facet. Search и status при этом сохраняются. Это одинаково действует для
common, exact dynamic и range dynamic facets.

Malformed expressions, missing Category, unknown/non-filterable attribute,
forbidden operator, invalid typed value, duplicate range boundary и invalid
availability/sort/order возвращают controlled HTTP 422 через CatalogError
contract. Invalid Category остаётся 404; broken versioned metadata остаётся
server-side CatalogSchemaError/500 без SQL details.

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

Миграция `a6b7c8d9e0f1`:

1. добавляет system Category `copper_network_cable` и пять metadata attributes;
2. добавляет два optional power-cable conductor attributes;
3. расширяет SFP form-factor/connector ENUM metadata значениями `XFP` и
   `SC Simplex`;
4. не читает `data/source/` и не импортирует Item или inventory state.

Миграция `a2b3c4d5e6f7`:

1. добавляет optional SFP attributes `speed_profile`, `reach_profile`,
   `wavelength_profile`, `nominal_wavelength_nm` со стабильными UUID;
2. добавляет exact connector values `MPO` и `MPO/PC`, не подменяя их
   `MPO/MTP`;
3. не создаёт Item, InventoryUnit, StockBalance или opening movement и не читает
   внешний workbook;
4. downgrade разрешён только пока ни один из новых SFP attributes не имеет
   ItemAttributeValue; при наличии хотя бы одного значения migration
   fail-fast останавливается до destructive DELETE;
5. безопасный downgrade без profile values удаляет только новую metadata и
   восстанавливает прежний connector vocabulary. После появления profile
   values rollback выполняется forward-fix либо восстановлением verified
   PostgreSQL backup, а не удалением этих значений.

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

На ORM relationship `Manufacturer.items` установлен `passive_deletes="all"`:
`session.delete(manufacturer)` не обнуляет nullable `Item.manufacturer_id`, а
передаёт решение PostgreSQL, где действующий reference блокирует DELETE через
`ON DELETE RESTRICT`.

Indexes ограничены текущими Stage 5 query patterns: category/status listing,
manufacturer FK, duplicate MPN, duplicate normalized name/model и FK/unique
lookups. Индексы для будущих faceted queries откладываются до появления
реальных запросов.

## Deliberately deferred

Stage 5 намеренно не реализовывал перечисленное ниже. Stage 6 теперь реализует
первые три группы в отдельном `WAREHOUSE_DOMAIN`; остальные пункты остаются
deferred:

- Movement/MovementLine (реализовано Stage 6);
- StockBalance и quantity positions (реализовано Stage 6);
- InventoryUnit/serial lifecycle (реализовано Stage 6);
- location, holder и custody (реализовано Stage 6);
- receiving/issuing/return/transfer/write-off (реализовано Stage 6);
- global search и faceted filters (реализовано Stage 7);
- media;
- Excel import/export;
- source quantities, balances или opening-balance import;
- frontend catalog/Admin/stock/«Моё» UI (реализовано Stage 8);
- Redis, Elasticsearch, queues или новые services.

## Source reference reconciliation

Legacy source reference review выполнен для трёх workbook, шести sheets и 176
непустых data rows. Результат и классификация A–F находятся в
`docs/CATALOG_SOURCE_REFERENCE.md`.

Подтверждены current Item/Manufacturer/identifier semantics, четыре
представленные initial category boundaries и metadata-driven typed EAV.
Recurring copper network cables потребовали отдельной system Category;
power-conductor semantics и два SFP tokens потребовали versioned metadata
refinement. Backend domain contract не менялся.

Для SFP этот legacy review superseded внешним read-only workbook
`~/dc-inventory-input/sfp-authoritative.xlsx`, sheet `На складе`. Audit всех 23
строк (265 физических модулей, 10 manufacturers) подтвердил lossless contract
выше: source `Модель` отображается только в `Item.model`, а
`manufacturer_part_number` и `internal_code` остаются `NULL` без отдельного
authoritative source. SFP остаётся `QUANTITY`; InventoryUnit не создаются.
Workbook не скопирован в repository и данные/количества не импортированы.
Будущий Stage 12 import обязан запросить явную destination Location и провести
opening quantities через movement semantics после снятия production-data gate.

Для остальных категорий остаются provisional или требуют human verification:

- optics connector/product-type/color/polarity vocabularies;
- power connector/color vocabularies;
- NIC PCIe/media notation, поскольку прямых NIC examples нет;
- disk sector format/endurance notation;
- ambiguous disk vendor/model/MPN strings.

Reference files не становятся runtime source of truth и не предназначены для
импорта существующего inventory. Quantity, balance, server placement, serial,
location и holder относятся к отдельному Stage 6 inventory domain, но source
workbooks по-прежнему не импортируются в него.
