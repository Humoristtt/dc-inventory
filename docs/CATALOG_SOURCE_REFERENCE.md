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

## Authoritative SFP opening source — отдельный contract

Исторические workbook ниже остаются только source reference для Stage 5 и их
inventory quantities по-прежнему не импортируются.

Отдельно от них для будущего первого реального SFP-ввода зафиксирован
authoritative workbook:

    ~/dc-inventory-input/sfp-authoritative.xlsx

Operational contract:

- файл внешний и read-only;
- файл и его копии `sfp-authoritative*.xlsx/.xlsm/.xls` не коммитятся в Git;
- рабочий sheet: `На складе`;
- 23 data rows;
- суммарное фактическое количество: 265;
- `Модель` маппится в `Item.model`, а не в manufacturer part number;
- отсутствующий P/N остаётся `NULL`;
- serial units для этого dataset не создаются;
- accounting mode — `QUANTITY`;
- Location нельзя выводить или придумывать из отсутствующего source field;
- старые S/N, WWN, P/N и historical HP/HPE grouping не переносятся;
- до закрытия Stage 15 workbook не импортируется в production;
- после ввода PostgreSQL становится runtime source of truth.

Этот authoritative dataset не отменяет historical source-reference решения
ниже: это другой файл с другой ролью и отдельным acceptance gate.

## Покрытие анализа

Проверены три workbook, шесть непустых sheets и 176 непустых data rows:

| Workbook | Sheets | Data rows | Полезный контекст |
|---|---|---:|---|
| `Инвентаризация SFP модулей.xlsx` | `На складе`, `IXcellerate` | 33 | SFP manufacturer и технические форматы |
| `Инвентаризация дисков в серверах.xlsx` | `Свод общих типов дисков`, `Диски`, `Общий список` | 109 | типы накопителей, интерфейсы, form factor, ёмкости, vendor/model formats |
| `Оптика и медь.xlsx` | `Лист1` | 34 | оптика, кабели питания и медные сетевые кабели |

Семь строк в `Общий список` не содержат disk product identity и полезны только
как operational context. Все остальные строки имеют хотя бы один catalog-bearing
field. Количество строк — coverage metric анализа, а не inventory quantity.

## Source-to-canonical mapping

### SFP / трансиверы

| Source semantic | Canonical contract | Решение |
|---|---|---|
| Производитель | `Manufacturer` | `Не указан` означает отсутствие manufacturer, а не отдельный бренд |
| Скорость, Gbit/s | `speed_mbps` | единица нормализуется в Mbps; single-rate decimal format поддерживается |
| Форм-фактор | `form_factor` | canonical uppercase form-factor token |
| Волокно | `medium` | `SM` → `SMF`, `MM` → `MMF`, медь → `Copper` |
| Дальность | `reach_m` | plain m/km переводится в metres; условные значения требуют ручного решения |
| Разъём | `connector` | polish/lane suffix не смешивается с canonical connector token |
| Длина волны | `tx_wavelength_nm`, `rx_wavelength_nm` | split выполняется только когда TX/RX явно указаны или подтверждены specs |
| Количество | Stage 6 inventory domain | не импортируется из reference source |

Reference подтверждает текущие SFP/SFP+/SFP28/QSFP+/QSFP28 formats и добавляет
стандартизованные `XFP` и `SC Simplex`. `MPO` и `MPO-12` канонизируются как
connector family `MPO/MTP`; lane/fiber count не выводится автоматически.

Одна multi-rate запись использует notation `10/25`. Required scalar
`speed_mbps` не меняется по одной строке: конкретное canonical значение требует
проверки product specs. Аналогично условная reach по OM3/OM4 и multi-wavelength
CWDM notation не преобразуются догадкой.

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
