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
    ├── catalog/        # следующий предметный этап
    └── inventory/      # последующий складской core

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

Текущий Alembic head после Stage 4:

    e8f1a2b3c4d5

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

## Планируемая предметная модель

До первой бизнес-миграции точная схема ещё не зафиксирована.

Уже реализованные identity/auth и Telegram delivery сущности описаны выше.

Реализованные инфраструктурные Stage 4 сущности:

- NotificationOutbox;
- TelegramUpdate;
- AccessDecisionCallback.

Планируемые предметные сущности:

- Category;
- CategoryAttribute;
- Item;
- InventoryUnit;
- Location;
- StockBalance;
- Movement;
- MovementLine;
- AuditEvent.

Список предметных сущностей является архитектурным направлением, а не уже
существующей складской схемой базы данных.

## Конкурентность

Складские операции должны выполняться транзакционно.

Критический acceptance-инвариант:

Если два пользователя одновременно пытаются получить последнюю доступную единицу оборудования, успешно завершиться должна только одна операция.

Точный механизм блокировок будет закреплён вместе с реализацией Inventory Core.

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

`statement_timeout` и `lock_timeout` относятся к runtime-запросам приложения. Alembic намеренно не получает короткий statement timeout, потому что будущие DDL-миграции могут законно выполняться дольше обычного API-запроса.

## Баланс как проекция журнала

`Movement` и его строки являются источником истории складских изменений.

`StockBalance`, если он используется, должен рассматриваться как транзакционно поддерживаемая проекция для быстрых чтений, а не как независимый источник истины. Любое изменение `StockBalance` должно происходить в той же транзакции, которая фиксирует соответствующее движение.

Историческая операция после проведения не редактируется. Исправления выполняются компенсирующим движением. Если системе понадобится черновик операции, состояние `draft` должно быть явно отделено от проведённого неизменяемого события.


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
