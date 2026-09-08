# Сверка каталога с source reference

## Статус и границы

Документ фиксирует сверку Stage 5 с локальными примерами из `data/source/`.
Файлы остаются untracked и не являются runtime dependency.

Продуктовое решение:

- source spreadsheets — только reference material для проектирования каталога;
- они не являются авторитетной inventory database или обязательным import source;
- существующие количества, остатки и иное operational state не импортируются;
- фактический stock будет проверен владельцем вручную при вводе оборудования;
- Stage 5 не создавал `InventoryUnit`, `StockBalance`, movements, locations или
  opening balances; Stage 6 реализует первые четыре понятия в отдельном
  warehouse domain, но эти workbook по-прежнему ничего туда не импортируют.

## Operational inventory boundary

Этот документ остаётся historical Stage 5 design/source-reference и не является
authoritative production inventory dataset.

Старые files/examples из `data/source/` по-прежнему не используются для
production stock.

После Stage15 initial production source был определён отдельно:

- внешний operator workbook `inventory.xlsx`;
- workbook хранится вне repository;
- workbook contract реализован в
  `backend/app/bootstrap/inventory_workbook.py`;
- production one-shot safety boundary реализован в
  `backend/app/bootstrap/production_inventory.py`;
- real workbook contents и runtime-only validation values не дублируются в
  public documentation;
- bootstrap уже выполнен и повторно не запускается.

Current active category/schema contract определяется
`docs/CATALOG_SCHEMA.md`, а warehouse semantics —
`docs/WAREHOUSE_DOMAIN.md`.

## Исторический source-review

Старые coverage metrics и локальные spreadsheets не являются current inventory
acceptance criteria и не используются для первоначального наполнения склада.

## Source-to-canonical mapping

### Оптические кабели

| Source semantic | Canonical contract | Решение |
|---|---|---|
| Тип `Оптика` и product description | `product_type`, `Item.name` | `product_type` остаётся TEXT; source label сам по себе не различает patch cord/uniboot/другие варианты |
| SM/MM | `fiber_mode` | стабильные ENUM values `SM`, `MM` |
| OM2/OM3/OM4 | `fiber_standard` | существующий ENUM достаточен; SM без стандарта не превращается автоматически в OS2 |
| LC/MPO/LCHD и suffixes | `connector_a/b`, `polish_a/b` | connector остаётся TEXT; UPC/APC отделяются только при однозначном notation |
| Duplex/12F | `fiber_count` | canonical integer 2/12 при однозначной product specification |
| Длина | `length_m` | DECIMAL metres |
| Type B | `polarity` | TEXT остаётся корректным: source показывает только один вариант и не доказывает полный vocabulary |
| Количество | Stage 6 inventory domain | не импортируется из reference source |

Connector vocabulary не переводится в ENUM: reference содержит LC, MPO,
LCHD, gender и PC/UPC notation в неоднородных комбинациях. Текущий TEXT contract
не теряет валидные product semantics и не требует опасной миграции existing
typed values.

### Кабели питания

| Source semantic | Canonical contract | Решение |
|---|---|---|
| CEE 7/7, IEC C13/C14, Type I | `connector_a/b` | TEXT сохраняется; полное направление должно проверяться при ручном вводе |
| Длина | `length_m` | DECIMAL metres |
| Цвет | `color` | TEXT; четыре reference colors не считаются исчерпывающим ENUM |
| 10A / 250V | `rated_current_a`, `rated_voltage_v` | существующие canonical units A/V |
| `3×0.75 mm²`-подобная запись | `conductor_count`, `conductor_cross_section_mm2` | два optional typed attributes добавлены versioned migration |
| Количество | Stage 6 inventory domain | не импортируется из reference source |

Conductor specification встречается в семи из восьми power-cable examples и
является повторяющейся характеристикой продукта, а не состоянием inventory.

### Медные сетевые кабели

Шесть recurring examples описывают RJ45–RJ45 UTP Cat 5e patch cords разной
длины. Они не соответствуют fiber-required schema `optics` и не являются
кабелями питания. Добавлена system category `copper_network_cable` с default
`QUANTITY` и metadata:

- required TEXT `connector_a`, `connector_b`;
- required DECIMAL `length_m` в metres;
- required TEXT `cable_category`;
- optional TEXT `shielding`.

`cable_category` и `shielding` остаются TEXT: один observed value каждого поля
недостаточен для полного controlled vocabulary, хотя сами поля являются
стабильными product semantics.

### Диски / накопители

| Source semantic | Canonical contract | Решение |
|---|---|---|
| HDD/SSD | `drive_type` | существующий contract покрывает examples |
| SATA/SAS + 6/12 Gbit/s | `interface`, `interface_speed_mbps` | interface и speed хранятся раздельно; speed нормализуется в Mbps |
| 2.5 / M.2 | `form_factor` | существующий ENUM покрывает examples |
| marketing capacity | `capacity_bytes` | canonical product capacity берётся с label/datasheet, не из OS-observed capacity |
| Disk vendor | `Manufacturer` | case variants нормализуются; `ATA` не принимается автоматически как manufacturer |
| Disk model strings | `model` / `manufacturer_part_number` | значение распределяется только после ручной идентификации; concatenated values не split-ятся догадкой |
| Hostname/IP/rack/U/server identity | deployment/location context beyond Stage 6 core | не относится к Item |
| Installed/procurement counts | inventory/procurement context | не импортируется |

Некоторые source cells с intended form factor `2.5` были сохранены Excel как
date-like values. Composite product text подтверждает смысл, но сам corrupted
cell не используется как canonical data. Source также смешивает marketing
capacity и observed capacity; это подтверждает необходимость ручной проверки,
а не import heuristics.

Прямых NIC examples в предоставленных workbook нет. NIC schema остаётся
versioned и provisional в частях PCIe/media notation; отсутствие примеров не
является основанием менять уже проверенный contract.

## Manufacturer, identifiers и duplicate candidates

Текущий общий contract подтверждён:

- `Manufacturer` — normalized canonical brand entity;
- `model` — product/model designation;
- `manufacturer_part_number` — manufacturer identifier, не global unique;
- `internal_code` — optional internal globally unique identifier;
- `name` — human-facing catalog title.

Source columns не дают стабильного правила, позволяющего автоматически
разделить model и MPN. Несколько disk cells объединяют brand prefix, model и
несколько identifiers. Поэтому fuzzy matching, automatic merge и destructive
deduplication не добавляются.

Детерминированные duplicate candidates остаются без изменений:

1. same category + manufacturer + normalized MPN;
2. fallback same category + manufacturer + normalized name + normalized model.

## Классификация решений A–F

### A. CURRENT CONTRACT IS CORRECT

- `Item` остаётся product definition, не physical instance;
- Manufacturer/model/MPN/internal-code semantics;
- typed EAV, canonical units и metadata-driven validation;
- current `sfp`, `optics`, `power_cable`, `disk` boundaries;
- deterministic duplicate-candidate strategy;
- optics/power connector and color fields остаются TEXT;
- disk capacity/interface/form-factor contract.

### B. DOCUMENTATION CLARIFICATION ONLY

- source files являются reference examples, не import source;
- source-to-canonical normalization rules и ambiguous-value policy;
- observed/marketing disk capacity distinction;
- `Не указан` и `ATA` не становятся manufacturers автоматически.

### C. VERSIONED CATALOG METADATA MIGRATION REQUIRED

- новая recurring category `copper_network_cable`;
- optional power attributes `conductor_count` и
  `conductor_cross_section_mm2`;
- SFP ENUM additions `XFP` и `SC Simplex`.

### D. BACKEND DOMAIN CONTRACT CHANGE REQUIRED

Нет. Существующий ORM/schema/service/API уже обслуживает изменения через
versioned metadata без category-specific code.

### E. FUTURE INVENTORY DOMAIN — OUT OF STAGE 5

- все количества, остатки, installed/procurement counts;
- server/host/rack/site/location context;
- holder/custody и current placement;
- serial number, WWN, firmware и состояние physical unit;
- movements, opening balances, issue/return/transfer/write-off.

### F. SOURCE EXAMPLE IS AMBIGUOUS / REQUIRES HUMAN DECISION

- multi-rate SFP `10/25` и выбор canonical primary speed;
- conditional reach OM3/OM4 и multi-channel wavelength notation;
- connector polish/gender/lane suffixes, когда product specs не подтверждены;
- disk model versus MPN и concatenated identifiers;
- rows с `ATA` в vendor field;
- date-corrupted disk form-factor cells;
- NIC vocabularies, поскольку прямых NIC examples нет.

Эти ambiguities не блокируют Stage 5 metadata refinement и не оправдывают
fuzzy/import logic.
