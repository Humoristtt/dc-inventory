# Warehouse domain

## Назначение

Stage 6 добавляет append-only складской журнал поверх Stage 5 catalog. `Item`
остаётся определением продукта; количество, размещение и custody не хранятся в
`Item` и не импортируются из reference spreadsheets.

Каноническая история — `Movement` и `MovementLine`. `StockBalance` и текущие
поля `InventoryUnit` являются только транзакционно поддерживаемыми проекциями
этой истории.

`Movement.journal_seq` — database-generated monotonic journal order. Он является
каноническим порядком ledger для history и projection reconciliation и не
зависит от wall clock или случайного UUID. `occurred_at` остаётся audit
timestamp, но не используется как причинный порядок current-state transitions.
Допустимы gaps в `journal_seq` после rollback: последовательность задаёт порядок,
а не требование непрерывной нумерации.

Каждый immutable `Movement` также фиксирует `line_count`. Deferred PostgreSQL
constraint triggers на header и lines проверяют при commit, что movement содержит
ровно `line_count` строк и их `line_no` образуют contiguous диапазон `1..N`.
Это позволяет собрать header и lines в одной transaction, но запрещает позже
дописать line к уже проведённому movement или сохранить неполный header.

## Сущности

### Location

`Location` — физическая точка хранения без преждевременной topology hierarchy.
Она имеет UUID, display `code`, детерминированный `normalized_code`, name,
optional description, `ACTIVE/ARCHIVED`, archive timestamp и обычные timestamps.

Code уникален case-insensitively после trim и collapse whitespace. Публичного
hard-delete нет. Локацию с текущим quantity balance или stored serial unit нельзя
архивировать. Исторические FK и snapshots остаются действительными после
архивации.

### InventoryUnit

`InventoryUnit` — один физический экземпляр только `SERIAL` Item. PostgreSQL
проверяет это composite FK `(item_id, item_accounting_mode)` и `SERIAL` check.
Unit не дублирует manufacturer/model/catalog attributes.

Unit-specific поля:

- serial number и его exact normalized identity;
- optional WWN и normalized WWN;
- optional physical-unit comment;
- current state и current location/holder;
- timestamps.

`asset_tag`, firmware и другие расширенные physical-unit metadata Stage 6
не реализует. Они deliberately deferred и при необходимости добавляются
отдельной versioned migration/API contract.

Serial и WWN нормализуются как trim + whitespace collapse + Unicode casefold,
без fuzzy matching и без удаления punctuation. Ограничение длины повторно
проверяется после `casefold`, который может увеличить строку. Уникальность
serial действует в scope одного `Item`; non-null normalized WWN глобально
уникален среди всех `InventoryUnit`, поскольку это физическая identity.
Одинаковый vendor serial в разных catalog products допустим.

Состояния:

- `STORED`: ровно одна current Location;
- `ISSUED`: ровно один current holder User;
- `WRITTEN_OFF`: нет current position; обычные операции запрещены;
- `VOIDED`: unit не входит в current inventory после reversal external-source
  addition либо correction-to-absent ошибочной записи и может быть повторно
  активирован новым приходом.

`WRITTEN_OFF` terminal для обычных operations. Только однократный reversal
write-off может вернуть unit в исходную position.

При reactivation `VOIDED` unit существующий non-null WWN нельзя заменить другим.
Если новый request не передал WWN, прежний WWN сохраняется; если unit ранее не
имел WWN, он может быть задан. Каждая serial `MovementLine` хранит
`wwn_snapshot`, поэтому позднее допустимое уточнение не меняет смысл истории.

### Movement и MovementLine

`Movement` — immutable operation header. Он хранит type, actor, source и
destination positions, optional purpose/comment, occurred timestamp,
idempotency data и optional link на original movement.

Каждая сторона position содержит максимум одно из:

- Location;
- holder User.

`MovementLine` хранит immutable `line_no`, сохраняющий исходный request order,
Item и ровно одну accounting shape:

- `QUANTITY`: positive integer quantity, без InventoryUnit;
- `SERIAL`: InventoryUnit identity, без aggregate quantity.

В одном movement разрешены quantity и serial lines. Один quantity Item и один
InventoryUnit не могут повторяться в одном movement. Все lines применяются одной
DB transaction либо не применяется ни одна.

Quantity — strict positive integer: bool, float и numeric string не
коэрсятся. Request ограничен максимумом PostgreSQL `BIGINT`; destination upsert
не выполняется, если сложение переполнит `BIGINT`, и возвращает controlled
`quantity_overflow`.

PostgreSQL `BEFORE UPDATE OR DELETE` triggers запрещают rewrite/delete
`movements` и `movement_lines`. Обычного mutation/delete API для history нет.

### StockBalance

`StockBalance` существует только для `QUANTITY` Item и содержит positive integer
quantity ровно в одной position: Location либо holder User. Два partial unique
indexes обеспечивают максимум один balance для `(Item, Location)` и максимум
один для `(Item, holder)`.

Нулевые строки удаляются; отрицательные и нулевые persisted balances запрещены
check constraint. Aggregate balance для SERIAL не создаётся: current state
каждой физической единицы хранит `InventoryUnit`.

## Movement types и positions

| Type | Source | Destination | Семантика |
|---|---|---|---|
| `RECEIPT` | external | Location | приход; serial identity создаётся или активируется из `VOIDED` |
| `ISSUE` | Location | holder User | остаток уходит со склада, holder получает custody |
| `RETURN` | holder User | Location | custody очищается, оборудование возвращается на склад |
| `TRANSFER` | Location | другая Location | складское перемещение |
| `WRITE_OFF` | Location или holder User | absent | quantity исчезает из current balance; serial становится `WRITTEN_OFF` |
| `CORRECTION` | optional position | optional different position | явное исправляющее state transition с обязательной ссылкой на original |
| `REVERSAL` | inverse original destination | inverse original source | точная компенсирующая операция для original lines |

`CORRECTION` не является редактированием original. Она обязана ссылаться на
существующий non-reversal movement, касаться хотя бы одной position original, а
каждая correction line обязана использовать Item из original. Эти минимальные
отношения проверяются service и PostgreSQL triggers; link означает конкретный
контекст исправления, а не произвольную audit association. Положительные lines
и явные source/destination positions поддерживают decrease, increase или
relocate без generic signed-delta API.

Для SERIAL только `WRITE_OFF` переводит unit в `WRITTEN_OFF`. `CORRECTION` из
current position в absent означает удаление ошибочно учтённого экземпляра и
переводит его в `VOIDED`; reversal такой correction возвращает unit, если он всё
ещё `VOIDED`.

`REVERSAL` создаётся отдельным endpoint; клиент не передаёт его lines. Backend
копирует identities/quantities original и меняет source/destination местами.
Reversal разрешён только если текущая projection допускает обратный transition.
Partial unique index допускает максимум один reversal для original. Reversal
нельзя reversal-ить; correction при необходимости может быть reversal-нут один
раз.

Location, в которой после операции появится current inventory, обязана быть
`ACTIVE`, включая destination reversal. Если exact reversal должен вернуть
inventory в archived Location, API возвращает `location_archived`; ADMIN сначала
явно unarchive Location.

## Archived Item lifecycle

Archive Item не удаляет и не блокирует уже существующий stock. Политика одинакова
для QUANTITY и SERIAL:

- новый `RECEIPT` запрещён;
- новый `ISSUE` запрещён;
- existing inventory разрешено `RETURN`, `TRANSFER` и `WRITE_OFF`;
- reversal разрешён, когда current state допускает точный inverse transition;
- correction archived Item разрешена только из existing source в Location либо
  absent; external-source correction и correction в holder запрещены, поэтому
  они не создают и не выдают новый archived inventory.

Catalog module при archive не импортирует inventory models и не вводит обратную
зависимость: policy применяется warehouse service при movement.

## Actor и custody

`actor_user_id` — authenticated ADMIN, который фиксирует movement.

`destination_holder_user_id` — recipient для `ISSUE`.
`source_holder_user_id` — фактический holder/source person для `RETURN` или
holder-side write-off. Это не actor, даже когда значения UUID совпадают.

Новый destination holder должен быть `APPROVED`. Возврат или write-off от уже
заблокированного/неактивного holder остаётся возможным для ADMIN, чтобы custody
можно было корректно закрыть.

## Snapshot policy

Stable FK сохраняются. Дополнительно immutable history хранит только display
данные, которые могут измениться и нужны для понимания операции:

- actor/source-holder/destination-holder display names;
- source/destination Location code и name;
- Item name, manufacturer name, model и MPN на каждой line;
- serial number и WWN на serial line.

Dynamic catalog attributes, descriptions, current access status и другие
операционные поля не snapshot-ятся: они либо не нужны для краткого смысла
movement, либо доступны по stable FK. Изменение Telegram username, Item name или
Location name не переписывает прошлые snapshots.

## Idempotency

Каждая movement mutation требует `client_request_id` длиной до 128 символов.
Scope ключа — actor User: unique `(actor_user_id, client_request_id)`.

Backend сохраняет SHA-256 fingerprint validated request:

- `client_request_id` перед fingerprint приводится к тому же trim + whitespace
  collapse значению, которое хранится и используется advisory lock;
- object keys JSON сортируются, но порядок lines сохраняется как значимый;
- остальные validated payload values, включая регистр и whitespace purpose,
  comment, serial и WWN, для fingerprint дополнительно не канонизируются;

- replay того же key и payload возвращает уже созданный Movement;
- тот же key с другим payload возвращает `409
  idempotency_payload_conflict`;
- transaction-scoped PostgreSQL advisory lock сериализует concurrent retries до
  проверки unique row.

Redis и process-local mutex не используются.

## Locking и transaction boundary

API открывает одну SQLAlchemy/PostgreSQL transaction на movement и делает один
commit после успешного service call. Ошибка приводит к rollback всего movement,
lines, balances, units и custody.

Lock order детерминирован:

1. idempotency advisory lock;
2. transaction-scoped advisory lock по UUID original Movement для correction /
   reversal; immutable original читается обычным `SELECT` без row-level UPDATE
   privilege;
3. все Location rows по UUID, затем все User rows по UUID;
4. все необходимые serial `(Item, normalized serial)` и global normalized WWN
   advisory locks единым sorted order;
5. non-locking discovery UUID reusable `VOIDED` units;
6. все InventoryUnit rows единым UUID order;
7. все Item rows единым UUID order;
8. source StockBalance rows по Item UUID;
9. atomic PostgreSQL upsert destination balances.

Identity парсится/нормализуется до locking. Existing-unit и reusable-unit paths
сходятся до row locks и больше не образуют `InventoryUnit -> Item` против
`Item -> InventoryUnit`. `SELECT ... FOR UPDATE` повторно проверяет current
source/state после ожидания concurrent transaction.

## API и permissions

Любой `Approved` пользователь может читать:

- `GET /api/inventory/locations[/{id}]`;
- `GET /api/inventory/stock`;
- `GET /api/inventory/units`.

Для обычного `USER` inventory read model использует least-privilege:

- общий stock и факт custody доступны для рабочего складского UX, но чужой
  holder обезличивается: `user_id=null`, display name=`Сотрудник`;
- `holder_user_id` filter для stock и units разрешён только для собственного
  User UUID; запрос чужого holder возвращает `403`;
- в общем списке serial units поля `serial_number`, `wwn`, `comment` и реальная
  identity holder доступны только для unit, который сейчас выдан этому USER;
  чужие и находящиеся на складе serial units возвращаются без этих private
  полей;
- `GET /api/inventory/units/{id}` обычному USER разрешён только для unit,
  который сейчас числится за ним; чужой или складской unit detail возвращает
  `403`;
- immutable movement journal не является пользовательским read API:
  `GET /api/inventory/movements[/{id}]` доступен только `ADMIN`.

`ADMIN` получает полные stock/unit representations, может фильтровать по любому
holder и читать полный immutable movement journal.

`Admin` mutation boundary:

- create/archive/unarchive Location;
- create Movement;
- reverse Movement.

Raw `IntegrityError` и SQL text наружу не передаются; domain errors используют
stable `{code, message}` detail. Только PostgreSQL `40P01`, `55P03` и `40001`
маппятся в safe `409 inventory_concurrency_conflict`; unrelated DB failures не
маскируются как conflict.

## Projection reconciliation и production-data gate

Read-only `backend/scripts/reconcile_inventory_projections.sql` независимо
пересчитывает QUANTITY positions и latest SERIAL state из canonical journal и
сравнивает их с `StockBalance`/`InventoryUnit`. Перед первым реальным вводом и
после restore оба result set обязаны быть пустыми; порядок запуска приведён в
`docs/DEVELOPMENT.md`.

Реальный inventory ввод остаётся заблокирован до реализации PostgreSQL backup,
создания проверяемого backup artifact и успешного реального restore test в
отдельное окружение. Stage 6 не является разрешением вводить production stock.

## Deliberately deferred

- frontend warehouse UI;
- USER self-service issue/return;
- opening-balance/import flow и любой Excel inventory import;
- opening quantities, seeded balances или seeded serial units;
- reservation, procurement и stocktake workflows;
- QR/barcode, media, notifications, export и global search;
- location hierarchy/topology;
- standalone HR/employee model;
- generic event-sourcing/CQRS infrastructure.

Будущие `OPENING_BALANCE` и `STOCKTAKE_ADJUSTMENT` workflows не входят в Stage 6.
Фактический начальный inventory будет введён только после production-data gate
через отдельно согласованный controlled workflow.
