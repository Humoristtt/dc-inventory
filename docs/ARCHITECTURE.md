# Архитектура

## Назначение

Система предназначена для инвентаризации оборудования и расходных материалов ЦОД с полной прослеживаемостью движения остатков.

Архитектурный стиль приложения — модульный монолит.

Компоненты разделяются по ответственности и предметным областям, но без преждевременного выделения микросервисов.

## Основной складской инвариант

Остаток оборудования нельзя изменять произвольным редактированием числа.

Любое изменение остатка должно происходить через складскую операцию:

- приход;
- выдача;
- возврат;
- перемещение;
- списание;
- корректировка или компенсирующая операция.

Исторические операции не должны незаметно изменяться задним числом.

Это позволяет восстанавливать происхождение текущего остатка и проводить аудит действий пользователей.

## Режимы учёта

### Количественный

Используется для однородных позиций, где достаточно учитывать количество.

Примеры:

- кабели;
- массовые трансиверы;
- расходные материалы.

### Серийный

Используется для оборудования, которое необходимо отслеживать индивидуально.

Примеры:

- HDD и SSD;
- сетевые карты;
- дорогостоящие трансиверы;
- другое оборудование с серийным номером.

## Backend

Текущая структура:

    backend/
    ├── alembic.ini
    ├── app/
    │   ├── api/
    │   │   ├── health.py
    │   │   └── router.py
    │   ├── core/
    │   │   └── config.py
    │   ├── db/
    │   │   ├── base.py
    │   │   ├── engine.py
    │   │   └── health.py
    │   ├── modules/
    │   └── main.py
    ├── migrations/
    ├── tests/
    └── pyproject.toml

`api` отвечает за HTTP-интерфейс.

`core` содержит общую конфигурацию приложения.

`db` содержит инфраструктуру доступа к PostgreSQL.

`modules` предназначен для предметных модулей приложения.

Бизнес-логика не должна накапливаться в `main.py`, глобальном `services.py` или других монолитных файлах.

По мере реализации ожидаются отдельные предметные области, например:

    modules/
    ├── auth/
    ├── identity/
    ├── notifications/
    ├── telegram_bot/
    ├── catalog/        # Category / Manufacturer / Item / typed attributes
    └── inventory/      # Location / ledger / balances / serial custody

Внутри предметного модуля API, schemas, service/repository и модели разделяются тогда, когда возникает соответствующая ответственность.

Искусственное дробление простого кода на большое количество файлов не требуется.

## Конфигурация

Backend использует `pydantic-settings`.

Обязательная настройка:

    DATABASE_URL

Дополнительно поддерживаются:

    APP_ENV
    DATABASE_CONNECT_TIMEOUT_SECONDS
    DATABASE_POOL_SIZE
    DATABASE_MAX_OVERFLOW
    DATABASE_POOL_TIMEOUT_SECONDS
    DATABASE_STATEMENT_TIMEOUT_SECONDS
    DATABASE_LOCK_TIMEOUT_SECONDS

Telegram authentication и webhook используют backend-only настройки:

    TELEGRAM_BOT_TOKEN
    TELEGRAM_INIT_DATA_MAX_AGE_SECONDS
    ADMIN_TELEGRAM_USER_ID
    SUPPORT_TELEGRAM_USERNAME
    AUTH_SESSION_TTL_SECONDS
    AUTH_COOKIE_NAME
    TELEGRAM_WEBHOOK_SECRET
    TELEGRAM_WEB_APP_URL

Отдельный notification worker использует:

    TELEGRAM_GATEWAY_URL
    TELEGRAM_GATEWAY_SECRET
    TELEGRAM_GATEWAY_TIMEOUT_SECONDS
    NOTIFICATION_WORKER_POLL_SECONDS
    NOTIFICATION_WORKER_CLAIM_TTL_SECONDS
    NOTIFICATION_WORKER_BATCH_SIZE
    NOTIFICATION_WORKER_MAX_ATTEMPTS

`TELEGRAM_BOT_TOKEN` нужен backend для серверной проверки подписи Telegram
`initData`. Он не передаётся frontend и не нужен migration container.
`telegram-worker` bot token также не получает: Bot API token хранится
Cloudflare Worker Secret.

Секреты не имеют production-default значений и не хранятся в Git.

Локальный `.env` игнорируется Git.

`.env.example` содержит только пример конфигурации.

## PostgreSQL

PostgreSQL является каноническим источником данных.

Runtime backend использует:

    SQLAlchemy 2 async
            ↓
        asyncpg
            ↓
        PostgreSQL

Для локальной разработки используется PostgreSQL 18 в Docker Compose.

Порт базы данных публикуется только на loopback development-машины:

    127.0.0.1:55432 -> PostgreSQL:5432

Это исключительно development-механизм. В `compose.dev.yaml` PostgreSQL
остаётся участником внутренней `db_net`, но дополнительно подключён к
`dev_host_net`, предназначенной только для loopback-публикации БД на
development host. `web` к `dev_host_net` не подключается и прямого доступа к
PostgreSQL не получает.

Production PostgreSQL host-порта не имеет и остаётся только во внутренней
`db_net`.


Production использует четыре отдельные PostgreSQL identity:

- owner/migrator — Alembic и permission bootstrap;
- backend runtime — application reads/writes по least-privilege contract;
- Telegram worker — notification delivery;
- maintenance worker — bounded technical retention.

Backend runtime не имеет общего `UPDATE` на immutable warehouse journal.
Для `telegram_updates` разрешён только `UPDATE(processed_at)`.
Controlled recovery `notification_outbox` ограничен delivery-state columns;
payload backend менять не может.

## Миграции

Миграции управляются Alembic.

Текущий baseline:

    48c2f07f01a0

Alembic использует тот же async PostgreSQL driver `asyncpg`, что и runtime приложения.

Строка подключения не хранится в `alembic.ini`.

Источник подключения:

    DATABASE_URL

Первая baseline-миграция намеренно не создаёт предметных таблиц и фиксирует начало migration history.

После baseline уже существуют foundation-миграции:

    7b0e3f6a9c21  User / TelegramIdentity / AccessRequest
    c4d8f2a1b903  server-side AuthSession
    e8f1a2b3c4d5  NotificationOutbox / TelegramUpdate / AccessDecisionCallback
    f4a5b6c7d8e9  Catalog foundation + five system category schemas
    a6b7c8d9e0f1  Source-backed catalog metadata refinement
    b7c8d9e0f1a2  Warehouse ledger + current-state projections
    c8d9e0f1a2b3  Technical-retention indexes
    d9e0f1a2b3c4  Catalog search, typed filters and inventory/facet read model

Текущий migration head:

    d9e0f1a2b3c4

Следующие предметные схемы добавляются отдельными миграциями.

## Health checks

Backend предоставляет два различных endpoint.

### Liveness

    GET /api/health/live

Проверяет, что процесс приложения способен обслуживать HTTP-запросы.

Не зависит от доступности PostgreSQL.

Успешный ответ:

    {"status":"ok"}

### Readiness

    GET /api/health/ready

Проверяет готовность приложения обслуживать полноценный трафик.

В текущей реализации выполняется `SELECT 1` через отдельный DB health layer.

Если PostgreSQL недоступен, endpoint возвращает HTTP 503.

После восстановления PostgreSQL readiness восстанавливается без рестарта backend.

Фактически проверенный lifecycle:

    DB UP   -> live 200 / ready 200
    DB DOWN -> live 200 / ready 503
    DB BACK -> live 200 / ready 200

## Identity, authentication и access control

Уже реализованные сущности:

    User
      ├── TelegramIdentity (1:1)
      ├── AccessRequest (1:N)
      └── AuthSession (1:N)

Внутренняя идентичность пользователя основана на UUID `User.id`.
Telegram является внешним identity provider. Пользователь сопоставляется по
числовому `telegram_user_id`; username не является идентификатором.

Первый ADMIN задаётся только явным `ADMIN_TELEGRAM_USER_ID`.

`AccessRequest` хранит историю отдельных запросов. Допустима ровно одна
активная запись `PENDING` на пользователя. `REJECTED` означает отказ по
конкретному запросу и допускает новый запрос. `BLOCKED` запрещает повторный
запрос.

Если configured bootstrap ADMIN уже существовал как обычный пользователь,
повторная Telegram-аутентификация восстанавливает `ADMIN + APPROVED` и
атомарно закрывает оставшийся `PENDING` access request.

Telegram WebApp authentication:

    original initData
        -> HMAC + auth_date validation
        -> TelegramIdentity upsert
        -> random server session token
        -> HttpOnly cookie

В PostgreSQL хранится только SHA-256 hash session token. Сессия имеет expiry и
может быть отозвана.

Backend различает:

    Authenticated -> валидная session
    Approved      -> Authenticated + APPROVED
    Admin         -> Approved + ADMIN

`Authenticated` нужен для собственного access-status API. Будущие складские
и административные endpoints обязаны использовать `Approved` или `Admin`.

## Предметная модель

Реализованные identity/auth и Telegram delivery сущности описаны выше.

Инфраструктурные Stage 4 сущности:

- NotificationOutbox;
- TelegramUpdate;
- AccessDecisionCallback.

Stage 5 фиксирует каталог:

- Category;
- Manufacturer;
- CategoryAttribute;
- Item;
- ItemAttributeValue.

`Item` является каталожной позицией, а не физическим serial unit. Технические
характеристики хранятся typed rows, управляемыми Category metadata; uncontrolled
JSON specification и category-specific nullable columns не используются.

Stage 6 фиксирует warehouse accounting core:

- Location;
- InventoryUnit;
- Movement;
- MovementLine;
- StockBalance.

`Movement`/`MovementLine` — append-only canonical history. `StockBalance`
существует только для quantity current positions, а mutable current state serial
unit хранится на `InventoryUnit`. Обе projections меняются только в одной
transaction с journal. Actor и physical source/destination holder представлены
разными User FK. Полный contract и deliberately deferred scope описаны в
`docs/WAREHOUSE_DOMAIN.md`.

Будущий administrative `AuditEvent` не смешивается с физическим movement
ledger и остаётся отдельной задачей.

## Catalog foundation

Канонический contract описан в `docs/CATALOG_SCHEMA.md`.

Основные решения:

- system Category и CategoryAttribute version-controlled через Alembic, без
  startup schema synchronization;
- Category machine key не зависит от локализованного display name;
- Manufacturer identity нормализуется через trim, whitespace collapse и
  `casefold`;
- Item имеет `QUANTITY/SERIAL` mode и `ACTIVE/ARCHIVED` lifecycle;
- category и accounting mode Item неизменяемы после создания;
- обычного hard-delete Item API нет;
- dynamic values хранятся в `ItemAttributeValue` с отдельными typed columns;
- PostgreSQL требует ровно одно populated typed value;
- redundant category ID и composite foreign keys запрещают cross-category
  attribute assignment на DB-level;
- DECIMAL хранится как `NUMERIC(30,10)`, API принимает exact decimal strings и
  до persistence ограничивает значение 20 integral и 10 fractional digits;
- ORM delete Manufacturer не обнуляет optional `Item.manufacturer_id`:
  `passive_deletes="all"` оставляет PostgreSQL `ON DELETE RESTRICT`
  авторитетным;
- duplicate detection возвращает candidates и не является destructive unique
  heuristic;
- read API использует существующую `Approved` boundary, mutation API —
  существующую `Admin` boundary.

Текущие versioned system schemas:

- SFP;
- optical cabling;
- copper network cabling;
- power cables;
- network interface cards;
- disks/drives.

Три локальных source workbook сверены как reference examples. Они не являются
inventory database или import source: quantity/balance/placement state не
переносится в catalog. Reference review добавил отдельную recurring copper
network cable Category, два power conductor attributes и два SFP vocabulary
tokens через migration `a6b7c8d9e0f1`. Неоднозначные connector/model/MPN и
multi-rate notations остаются manual decisions, а schema definitions —
deterministic versioned reference data.

## Catalog read/query layer

Stage 7 сохраняет `Item` root relation и не строит один размножающий строки JOIN
catalog EAV + StockBalance + InventoryUnit. Search, location и dynamic filters
используют correlated EXISTS. QUANTITY/SERIAL current counts собираются одним
aggregate subquery и используются list response, availability и sorting.
Pagination и total поэтому работают по unique Item rows; attributes выбранной
страницы загружаются существующим set-based loader.

Immutable `CatalogQuerySpec` является единым validated input для item list и
facets. Category behavior определяется CategoryAttribute metadata. Facet base
query переиспользует тот же predicate builder и исключает только predicate
вычисляемого facet. Contains search использует escaped bound LIKE/ILIKE values;
`pg_trgm` GIN indexes и typed EAV indexes добавлены migration
`d9e0f1a2b3c4`. Warehouse journal/projection write path Stage 6 не изменён.

## Конкурентность

Складские операции выполняются транзакционно в PostgreSQL. Idempotency retries
сериализуются transaction-scoped advisory lock по `(actor, client_request_id)`.
Correction/reversal дополнительно сериализуют original Movement context через
transaction-scoped advisory lock по UUID original movement. Сам immutable
Movement читается обычным `SELECT`, поэтому backend runtime-role не требует
`UPDATE` privilege для PostgreSQL row locking. Все Location rows затем берутся
в UUID order, после них User rows. Затем serial/WWN identity advisory locks
берутся единым sorted order; reusable UUID обнаруживаются без row lock; затем все
InventoryUnit rows блокируются в UUID order, после них все Item rows, затем
source StockBalance rows по Item UUID. Destination quantity balances изменяются
atomic PostgreSQL upsert с guard от `BIGINT` overflow. Existing-unit и
new/reusable-unit paths используют один порядок `InventoryUnit -> Item`.

Archived Item не является dependency catalog -> inventory: warehouse service
сам запрещает новый receipt/issue, но разрешает existing return/transfer/
write-off и допустимый reversal. Destination Location любого movement, включая
reversal, обязана быть ACTIVE. Non-null normalized WWN глобально уникален среди
InventoryUnit; serial остаётся уникальным в Item scope.

Критический acceptance-инвариант:

Если два пользователя одновременно пытаются получить последнюю доступную единицу оборудования, успешно завершиться должна только одна операция.

Real PostgreSQL regression tests одновременно выдают последний quantity balance
и один serial unit двумя независимыми sessions. В обоих случаях ровно одна
transaction commits, вторая получает controlled domain conflict. Дополнительная
race regression сталкивает VOIDED-unit reactivation с reversal того же unit и
подтверждает отсутствие mixed lock-order deadlock.

## Целевая runtime-схема

    Telegram Mini App
            ↓
        Cloudflare
            ↓
    Cloudflare Tunnel
            ↓
          Nginx
       ├── React
       └── FastAPI
              ↓
          PostgreSQL

Telegram-уведомления:

    Application transaction
            ↓
    NotificationOutbox
            ↓
          worker
            ↓
    Telegram Gateway
            ↓
    Telegram Bot API

Gateway необходим из-за недоступности `api.telegram.org:443` напрямую с production VM.

## Безопасность

- Telegram `initData` должен обязательно проверяться backend.
- Данным пользователя из Telegram WebApp нельзя доверять до серверной проверки подписи.
- PostgreSQL не публикуется в интернет.
- Production VM имеет read-only доступ к GitHub.
- Production deployment выполняется из конкретного проверенного Git commit.
- Секреты не хранятся в Git.
- Складские операции должны быть атомарными и транзакционными.

## Runtime hardening до предметной схемы

До первой бизнес-миграции закреплены инфраструктурные инварианты, которые дешевле определить заранее:

- SQLAlchemy `MetaData` использует единый naming convention для PK/FK/UQ/IX/CK;
- runtime DB pool имеет явные границы размера и ожидания;
- для runtime-соединений заданы `statement_timeout` и `lock_timeout`;
- PostgreSQL-сессии backend работают в UTC;
- production OpenAPI/Swagger отключены;
- Nginx корректно сохраняет исходную HTTPS-схему Cloudflare и IP посетителя;
- Uvicorn принимает proxy headers только внутри закрытой application-сети;
- PostgreSQL отделён от web отдельной внутренней Docker-сетью;
- CI поднимает production-shaped Compose и проверяет полный маршрут Nginx -> FastAPI -> PostgreSQL.

Runtime и migration timeout budgets разделены. Обычные backend-запросы
используют `DATABASE_STATEMENT_TIMEOUT_SECONDS` /
`DATABASE_LOCK_TIMEOUT_SECONDS`, а Alembic получает отдельные более широкие
`MIGRATION_STATEMENT_TIMEOUT_SECONDS` / `MIGRATION_LOCK_TIMEOUT_SECONDS`.
Это ограничивает зависшие DDL/lock waits, не приравнивая миграцию к обычному
API-запросу.

## Баланс как проекция журнала

`Movement` и его строки являются источником истории складских изменений.

`StockBalance`, если он используется, должен рассматриваться как транзакционно поддерживаемая проекция для быстрых чтений, а не как независимый источник истины. Любое изменение `StockBalance` должно происходить в той же транзакции, которая фиксирует соответствующее движение.

Историческая операция после проведения не редактируется. Исправления выполняются компенсирующим движением. Если системе понадобится черновик операции, состояние `draft` должно быть явно отделено от проведённого неизменяемого события.

Stage 6 реализует это как positive-integer `StockBalance` row ровно для одной
Location либо holder User. Partial unique indexes запрещают duplicate positions,
а check constraints запрещают zero/negative persisted rows. `Movement` и
`MovementLine` защищены PostgreSQL triggers от `UPDATE/DELETE`; immutable
`Movement.line_count` и deferred constraint triggers дополнительно требуют на
commit ровно полный contiguous набор `MovementLine.line_no = 1..line_count`.
Поэтому после commit к существующему movement нельзя дописать новую line.
Reversal создаёт новый movement, ссылается на original и ограничен одним partial
unique index. Immutable `MovementLine.line_no` сохраняет request order; correction link
дополнительно обязан иметь общую original position и только original Items.

Перед реальными production inventory данными read-only reconciliation
`backend/scripts/reconcile_inventory_projections.sql` должен вернуть zero drift
для quantity и serial projections. Сам ввод остаётся заблокирован до готового
PostgreSQL backup и успешного real restore test в отдельное окружение.


## Frontend access-state authority

Frontend cache не является authorization boundary: backend `Approved` / `Admin`
остаётся обязательным для защищённых API.

Для access-gate закреплены дополнительные инварианты:

- access query key включает `user.id`, поэтому состояние разных Telegram users не
  переиспользуется;
- данные `/api/access-requests/me` имеют право уточнять UI-state только пока
  актуальный `/api/auth/me` сообщает `PENDING`;
- свежие `REJECTED` / `BLOCKED` / `APPROVED` из auth-state не могут быть
  перезаписаны старым access cache;
- переход `REJECTED -> PENDING` после успешного повторного запроса синхронизируется
  в auth cache явно;
- polling останавливается после выхода из `PENDING`.

## Frontend catalog navigation and server state

`TelegramAccessGate` остаётся внешней границей всего React-приложения. После
`APPROVED` внутри неё работает единый application shell с URL routes
`/catalog`, `/catalog/:categoryKey`, `/catalog/items/:itemId` и placeholder
routes будущих разделов. Второй auth state или frontend tokens не создаются.

Catalog frontend разделяет два вида состояния:

- search/filter/sort navigation state хранится в нормализованных
  `URLSearchParams`, поэтому history, reload и возврат из Item detail
  воспроизводимы;
- server responses хранятся в TanStack Query cache с детерминированными keys;
  limit/offset pages добавляются без дублирования Item.

URL navigation state изменяется ownership-specific updates: search меняет
только `q`, sort — только `sort/order`, filter sheet — только status,
manufacturer/location/availability и metadata filters. Каждый update сначала
читает актуальные `URLSearchParams`, поэтому отложенный debounce или старый
filter draft не может откатить более новое состояние другого owner. Search
input синхронизируется с back/reload/external URL без принудительного remount.

Item list сохраняет previous pages во время progressive refetch. Facets этого
не делают: при смене facet query UI показывает loading state и не выдаёт counts
предыдущего query за актуальные.

Catalog API encoding централизован в typed same-origin client. Repeated
`manufacturer_id`, `location_id` и metadata attribute `filter` parameters
сортируются и кодируются детерминированно. Filter UI получает common/dynamic
facets от backend и CategoryAttribute metadata; category-specific query logic в
React не допускается.

Telegram wrapper владеет `ready`/`expand`, runtime safe-area values и полным
BackButton subscribe/unsubscribe lifecycle. На `/catalog` BackButton скрыт; на
внутреннем route он возвращает по SPA history, а direct deep link безопасно
возвращается на `/catalog` без закрытия Mini App.


## Telegram delivery и access decisions

Stage 4 использует transactional outbox: доменная транзакция сохраняет Telegram
command в PostgreSQL, а отдельный worker выполняет сетевую доставку после commit.

`telegram-worker` claim-ит rows через `FOR UPDATE SKIP LOCKED`, использует lease
(`claimed_at` + `claim_token`) и at-least-once semantics. Incoming webhook
защищён Telegram secret token и persistent `telegram_updates.update_id` dedupe.

Inline callback содержит только opaque token. Request/user/action разрешаются
сервером, а решение может выполнять только Telegram identity с
`ADMIN + APPROVED`. AccessRequest и User блокируются `FOR UPDATE`.

Исходящая доставка идёт через Cloudflare Telegram Gateway. Bot token хранится
как Cloudflare Worker Secret; production `telegram-worker` получает только
gateway URL и отдельный gateway secret. Gateway имеет фиксированный allowlist
Bot API methods.


Telegram `update_id` является внешним natural key и не генерируется PostgreSQL:
для `telegram_updates.update_id` отключён autoincrement/sequence.

Terminal user access state является server-authoritative: stale PENDING request
или callback не может понизить/переписать `APPROVED`, `REJECTED` или `BLOCKED`.
Frontend также не применяет поздний `POST /api/access-requests -> PENDING`
поверх уже полученного `APPROVED`/`BLOCKED`.

## Access notification recovery и Telegram SDK delivery

Повторный explicit access request при уже существующем `PENDING`
AccessRequest не создаёт новый request.

Если ADMIN notification с тем же business dedupe key исчерпала retry и стала
`DEAD`, backend переиспользует существующую approve/reject callback pair и
controlled-upsert возвращает только terminal `DEAD` outbox row в `PENDING`.

Backend не имеет table-level `UPDATE notification_outbox`: разрешены только
delivery-state columns. Изменение payload запрещено DB-role contract.

Telegram Web App SDK поставляется same-origin:

    /vendor/telegram/telegram-web-app.js

CI фиксирует ожидаемый SHA-256 и размер vendored SDK. Frontend различает:

- успешную загрузку SDK;
- `load-error`;
- timeout;
- настоящий запуск вне Telegram.

Ошибка доставки SDK не маскируется сообщением «откройте приложение через
Telegram».
