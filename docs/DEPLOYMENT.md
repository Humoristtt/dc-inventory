# Развёртывание

## Принцип

Production VM не является development-машиной.

Изменения проходят следующий путь:

    Mac
      -> Git
      -> GitHub
      -> проверенный commit
      -> production VM

Production VM имеет read-only GitHub Deploy Key. Deploy выполняется только из конкретного SHA, успешно прошедшего CI.

Точный production Git checkout и реально запущенные backend/web artifacts
проверяются отдельно; один SHA не используется как смешанная checkout/runtime
истина.

Current accepted production Alembic head после RBAC cutover:

    b2c3d4e5f6a7

Текущий source Alembic head:

    b2c3d4e5f6a7

Stage15A automated off-VM backup, Stage15B real isolated restore и Stage15
technical hardening — `PASS`.

Warehouse Domain V2 и initial production inventory bootstrap приняты.

Regular warehouse mutation API остаётся fail-closed:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Initial bootstrap не требовал открытия этого gate: для него используется
отдельный guarded one-shot production path.

Stage15 historical acceptance описан в `docs/STAGE15_PLAN.md`.
Текущий operational state описан в `docs/OPERATIONS.md`.

## Production runtime

Production Compose находится в `compose.yaml`.

Схема:

    Telegram / Browser
          ↓
       Cloudflare
          ↓
    Cloudflare Tunnel
          ↓
    127.0.0.1:8080
          ↓
        Nginx
       ├── React
       └── /api
            ↓
          FastAPI
            ↓
        PostgreSQL

На host публикуется только:

    127.0.0.1:8080

Backend и PostgreSQL host-портов не имеют.

PostgreSQL и migration container находятся в отдельной внутренней Docker-сети. Nginx не имеет прямого сетевого доступа к PostgreSQL.

## Cloudflare Tunnel

`cloudflared` работает на production VM как systemd service и подключается к локальному origin:

    http://localhost:8080

Ожидаемый публичный hostname Mini App:

    https://app.spik-inventory.ru

Tunnel token является секретом и не хранится в Git или документации.

## Reverse proxy

Cloudflare передаёт исходную схему запроса в `X-Forwarded-Proto`, а IP посетителя — в `CF-Connecting-IP`.

Nginx нормализует эти значения и передаёт backend `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Real-IP` и `X-Forwarded-For`.

Nginx также выставляет `Strict-Transport-Security: max-age=31536000` на всех public response scopes. Публичный клиент получает этот header через Cloudflare HTTPS. `includeSubDomains` и `preload` намеренно не включены без отдельного доменного инварианта.

Uvicorn доверяет proxy headers, потому что production backend не публикуется на host и доступен только через внутреннюю application-сеть.

Nginx применяет rate limiting после нормализации `CF-Connecting-IP`: общий API ограничен до 30 запросов/с на клиента с burst 60; `POST /api/auth/telegram` и `POST /api/access-requests` дополнительно ограничены до 10 запросов/мин с burst 5. Telegram webhook вынесен в отдельный лимит 50 запросов/с с burst 100, чтобы Telegram delivery burst не конкурировал с пользовательским API. Превышение ingress-лимита возвращает HTTP `429`.

## Runtime resource limits

Production Compose ограничивает CPU и RAM каждого container service через `cpus` и `mem_limit`.

Defaults рассчитаны для текущей production VM с 4 vCPU и примерно 8 GiB RAM. Основные постоянные сервисы ограничены так, чтобы Docker workloads не могли вытеснить host OS и runtime overhead из памяти.

Значения можно переопределять через соответствующие `*_CPUS_LIMIT` и `*_MEMORY_LIMIT` variables без изменения Compose-файла.

## Supply-chain pinning

Runtime-changing application build выполняется с exact Git revision:

    REVISION="$(git rev-parse HEAD)"
    APP_REVISION="$REVISION" docker compose build backend postgres web

Backend/frontend Dockerfiles сохраняют revision в
`org.opencontainers.image.revision`.

Внешние container images в production/runtime, development и CI фиксируются одновременно human-readable tag и immutable `sha256` manifest digest. GitHub Actions фиксируются полным commit SHA; major version остаётся только комментарием для читаемости.

Required backend CI gate проверяет Dockerfile, Compose, CI service images и GitHub Actions и отклоняет возврат mutable external execution references.

Обновление pin выполняется явно: сначала выбирается новая версия/tag, затем проверяется upstream digest или Action commit SHA, после чего новый immutable reference проходит обычные runtime/CI gates.

## Секреты

Production `.env` создаётся непосредственно на VM и не хранится в Git.

Production DB bootstrap использует четыре PostgreSQL identity:

    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD

    POSTGRES_RUNTIME_USER
    POSTGRES_RUNTIME_PASSWORD

    POSTGRES_WORKER_USER
    POSTGRES_WORKER_PASSWORD

    POSTGRES_MAINTENANCE_USER
    POSTGRES_MAINTENANCE_PASSWORD

`POSTGRES_USER` — owner/migrator. Backend, Telegram worker и maintenance worker
используют отдельные least-privilege логины. Owner credentials runtime services
не получают.

Backend Telegram/auth boundary использует:

    TELEGRAM_BOT_TOKEN
    TELEGRAM_INIT_DATA_MAX_AGE_SECONDS
    ADMIN_TELEGRAM_USER_ID
    NOTIFICATION_TELEGRAM_USER_ID
    SUPPORT_TELEGRAM_USERNAME
    AUTH_SESSION_TTL_SECONDS
    AUTH_COOKIE_NAME
    TELEGRAM_WEBHOOK_SECRET
    TELEGRAM_WEB_APP_URL

`TELEGRAM_BOT_TOKEN` нужен backend для server-side HMAC-проверки Telegram
`initData`. Это тот же Telegram-issued credential, который Cloudflare Worker
хранит независимо как secret `BOT_TOKEN` для Bot API. Frontend его никогда не
получает.

`ADMIN_TELEGRAM_USER_ID` используется только как bootstrap/recovery OWNER
identity. `NOTIFICATION_TELEGRAM_USER_ID` — отдельный получатель operational
Telegram-уведомлений о запросах доступа и выдаче оборудования. Для обработки
inline access-decision кнопок этот Telegram user должен соответствовать
APPROVED ADMIN или OWNER в приложении.

### Guarded recovery OWNER rotation

Передача recovery OWNER выполняется только как maintenance-only operator
operation. Обычный HTTP API и UI не назначают OWNER.

Prerequisites:

- новый владелец уже хотя бы один раз прошёл Telegram authentication и имеет
  существующие `User` / `TelegramIdentity`;
- у target отсутствует outstanding equipment custody;
- получен fresh verified off-VM PostgreSQL backup;
- `web`, `backend`, `telegram-worker` и `maintenance-worker` остановлены;
- PostgreSQL остаётся healthy;
- production `.env` всё ещё содержит Telegram ID текущего OWNER.

Команда выполняется из target release image:

    docker compose --env-file .env -f compose.yaml run --rm --no-deps backend \
      python -m app.bootstrap.recovery_owner_rotation \
      --current-telegram-user-id CURRENT_TELEGRAM_ID \
      --target-telegram-user-id TARGET_TELEGRAM_ID \
      --target-user-id TARGET_USER_UUID \
      --confirm ROTATE_RECOVERY_OWNER

Одна PostgreSQL transaction под identity-management advisory lock:

1. проверяет, что configured recovery identity является единственным OWNER;
2. блокирует current/target user rows;
3. fail-closed проверяет target identity и custody;
4. переводит старого OWNER в ADMIN с `UserRoleEvent`;
5. переводит target в APPROVED при необходимости с `UserAccessEvent`;
6. завершает pending access request target при его наличии;
7. переводит target в OWNER с `UserRoleEvent`;
8. отзывает активные auth sessions обоих пользователей;
9. проверяет, что OWNER снова ровно один и это target.

После успешного commit runtime запускать ещё нельзя. Сначала production `.env`
обязательно изменяется на новый `ADMIN_TELEGRAM_USER_ID`, затем запускается
только новый runtime и выполняется auth/RBAC smoke.

Если transaction успешна, но `.env` ещё не обновлён, backend запускать
запрещено: старый configured recovery ID конфликтует с новым OWNER и recovery
reconciliation fail-closed.

В production `TELEGRAM_WEB_APP_URL` задаёт ровно публичный HTTPS origin Mini
App: без credentials, path, query, fragment и surrounding whitespace. Допустим
корневой `/` и явный TCP port. Стандартный HTTPS port `443` при same-origin
проверке канонизируется как обычный HTTPS origin без явного порта.
Этот origin одновременно используется WebApp-кнопками, same-origin asset
branded `/start` и защитой cookie-authenticated mutations по `Origin`.

Отдельный `telegram-worker` использует:

    TELEGRAM_GATEWAY_URL
    TELEGRAM_GATEWAY_SECRET
    TELEGRAM_GATEWAY_TIMEOUT_SECONDS
    NOTIFICATION_WORKER_POLL_SECONDS
    NOTIFICATION_WORKER_CLAIM_TTL_SECONDS
    NOTIFICATION_WORKER_BATCH_SIZE
    NOTIFICATION_WORKER_MAX_ATTEMPTS

`telegram-worker` не получает bot token, webhook secret или ADMIN ID.

В production `TELEGRAM_GATEWAY_URL` обязан быть абсолютным HTTPS URL без
credentials, query, fragment или surrounding whitespace. HTTP разрешён только
для development/internal test configuration.


Cloudflare Worker имеет собственное secret storage:

    BOT_TOKEN
    GATEWAY_SECRET

`BOT_TOKEN` должен содержать то же значение Telegram bot token, что backend
получает через `TELEGRAM_BOT_TOKEN`; secret stores при этом независимы.
`GATEWAY_SECRET` — другой credential: отдельный shared secret между production
`telegram-worker` и Cloudflare Worker.

При ротации Telegram bot token необходимо согласованно заменить backend
`TELEGRAM_BOT_TOKEN` и Cloudflare `BOT_TOKEN`. Секреты Cloudflare не хранятся
в Git.

Migration container получает owner/migration DB-конфигурацию.
После успешного Alembic upgrade одноразовый `db-permissions` container
идемпотентно применяет runtime/worker/maintenance grants.
Runtime containers не используют owner role.

`DATABASE_URL` внутри Docker network должен использовать hostname `postgres`.

Пример формы:

    postgresql+asyncpg://USER:PASSWORD@postgres:5432/DATABASE

## Telegram runtime boundary

Входящий маршрут:

    Telegram
      -> https://app.spik-inventory.ru/api/telegram/webhook
      -> Cloudflare
      -> Tunnel
      -> Nginx
      -> FastAPI

Webhook проверяет `X-Telegram-Bot-Api-Secret-Token`, а обработанные
`update_id` дедуплицируются в PostgreSQL.

Исходящий маршрут:

    application DB transaction
      -> notification_outbox
      -> telegram-worker
      -> Cloudflare Worker Telegram Gateway
      -> Telegram Bot API

Прямой outbound к Telegram Bot API с production VM не используется.

Cloudflare Gateway принимает ограниченный Bot API allowlist:

    sendMessage
    sendPhoto
    deleteMessage
    editMessageText
    editMessageReplyMarkup
    answerCallbackQuery

`sendPhoto` используется branded `/start` welcome, а `deleteMessage` —
best-effort cleanup incoming `/start` и предыдущего welcome. Gateway остаётся
deny-by-default для методов вне allowlist.

Запросы `telegram-worker` защищены отдельным gateway secret.
HTTP-клиент использует явный service `User-Agent`, чтобы Cloudflare edge
не блокировал стандартный Python urllib client кодом `1010`.

На чистой БД configured recovery identity должен хотя бы один раз открыть
Mini App и пройти Telegram authentication: auth flow создаёт `TelegramIdentity`
и bootstrap OWNER. Production использует текущую five-role RBAC model.

## Миграции

### RBAC maintenance cutover `f8a9b0c1d2e3 -> a1b2c3d4e5f6`

Migration `a1b2c3d4e5f6` не является backward-compatible со старым runtime:
она атомарно переводит persisted role `USER` в `ENGINEER`, тогда как
pre-RBAC backend понимает только historical `USER / ADMIN`.

Поэтому deploy, пересекающий этот migration boundary, выполняется только как
planned maintenance cutover. Запрещено оставлять старый backend работающим
параллельно с применением `a1b2c3d4e5f6`.

Обязательный порядок:

1. подтвердить exact target SHA и успешный CI;
2. получить свежий verified off-VM PostgreSQL backup;
3. подготовить новые immutable release artifacts;
4. остановить `web`, `backend`, `telegram-worker` и `maintenance-worker`;
5. убедиться, что старый application runtime больше не обращается к БД;
6. оставить PostgreSQL healthy и выполнить `alembic upgrade head`;
7. выполнить idempotent `db-permissions`;
8. запустить только новый runtime из target SHA;
9. дождаться health и выполнить auth/RBAC smoke;
10. убедиться, что configured recovery identity возвращается как `OWNER`.

После применения `a1b2c3d4e5f6` запрещено запускать pre-RBAC backend против
этой БД. Rollback выполняется forward-fix либо восстановлением verified
pre-cutover backup; запуск старого application image поверх migrated schema
не является допустимым rollback path.

Schema downgrade этой migration допускается только до появления RBAC state,
которое historical `USER / ADMIN` model не может представить. Downgrade
fail-closed запрещён, если существует `SENIOR_ENGINEER`, `MANAGER`, `OWNER`
или хотя бы один immutable `user_role_events` record. В таком состоянии
поддерживаемый rollback path — forward-fix либо restore verified pre-cutover
backup; audit history не удаляется ради downgrade.

Перед backend запускается одноразовый контейнер:

    alembic upgrade head

Backend запускается только после успешного завершения migration container.

Migration connection имеет отдельный bounded timeout budget:

    MIGRATION_STATEMENT_TIMEOUT_SECONDS=300
    MIGRATION_LOCK_TIMEOUT_SECONDS=5

`statement_timeout` ограничивает максимальную длительность одного SQL statement
миграции, а `lock_timeout` не позволяет Alembic бесконечно ждать занятый
PostgreSQL lock. Эти значения отделены от runtime
`DATABASE_STATEMENT_TIMEOUT_SECONDS` / `DATABASE_LOCK_TIMEOUT_SECONDS`, потому
что DDL-миграции и обычные API-транзакции имеют разный профиль выполнения.

Предметные миграции должны быть безопасны для последовательного deploy. Для
потенциально разрушительных изменений обязателен backup и заранее определённый
rollback/forward-fix plan.

Migration `a2b3c4d5e6f7` допускает schema downgrade только пока новые SFP
profile attributes не содержат данных. Если существует хотя бы один такой
`ItemAttributeValue`, downgrade fail-fast завершается без удаления значений.
В этом состоянии production rollback выполняется forward-fix либо
восстановлением verified PostgreSQL backup; destructive Alembic downgrade
не является допустимым rollback path.

## Initial production inventory bootstrap

Initial production bootstrap принят 2026-09-08.

Canonical entry point:

    python -m app.bootstrap.production_inventory

Это one-shot operator tool, а не обычный runtime mutation API.

Fail-closed contract:

- `APP_ENV=production`;
- PostgreSQL boundary — Docker hostname `postgres`;
- `REAL_INVENTORY_MUTATIONS_ENABLED` обязан оставаться `false`;
- explicit confirmation token обязателен;
- source SHA-256 передаётся runtime-параметром;
- expected workbook rows/items/quantity передаются runtime-параметрами;
- source workbook не хранится в repository;
- warehouse domain должен быть пуст;
- actor должен быть existing APPROVED ADMIN;
- location создаётся внутри той же transaction;
- initial inventory создаётся одной RECEIPT;
- post-write counts, total quantity и projection reconciliation проверяются до
  commit;
- любая ошибка откатывает transaction;
- повторный bootstrap в наполненную production DB fail-closed запрещён.

Реальные source values, workbook hash, actor/location identifiers и inventory
dataset намеренно не фиксируются в public repository documentation.

После успешного bootstrap обязательны read-only DB verification, health check,
zero-drift reconciliation и fresh verified off-VM backup.

## Проверка после deploy

    curl http://127.0.0.1:8080/healthz
    curl http://127.0.0.1:8080/api/health/live
    curl http://127.0.0.1:8080/api/health/ready

Ожидается HTTP 200 для всех трёх запросов.

Также проверяются:

- `postgres`, `backend`, `web` — healthy;
- `telegram-worker` — `Up`;
- `maintenance-worker` — `Up`;
- в maintenance logs есть успешная `technical retention:` iteration;
- `migrate` — `Exited (0)`;
- `db-permissions` — `Exited (0)`;
- на host отсутствуют listen-порты `8000` и `5432`;
- backend работает от UID 10001;
- web работает от пользователя `nginx`;
- для runtime-changing deploy production worktree соответствует утверждённому deploy commit;
- source-only sync, затрагивающий только documentation и host-side `ops/`
  tooling, может продвигать production worktree без rebuild/restart application
  containers, если Docker build contexts и application runtime source не
  менялись; изменённые host-side tools обязаны отдельно пройти
  syntax/contract checks.

Для Telegram delivery после runtime-changing deploy выполняется минимальный live
smoke: `/start` должен пройти webhook/outbox/worker/Gateway, удалить входящую
команду best-effort и вернуть branded `sendPhoto` welcome с caption и WebApp
button. Same-origin asset `/telegram/start-welcome.png` должен публично
отдаваться через production web path.

Для access acceptance используется отдельный пользователь:
request → ADMIN approve → user notification → вход в Mini App.

## Backup

Stage15A automated off-VM PostgreSQL backup и Stage15B real isolated restore
приняты.

Canonical command-level recovery procedure:

    docs/RECOVERY_RUNBOOK.md

Initial real inventory bootstrap уже принят. Перед любым следующим risky
schema/data change обязателен fresh verified backup и соответствующий
reconciliation/rollback plan.

## Technical data retention

Production uses a dedicated `maintenance-worker` and a separate
least-privilege PostgreSQL login. The maintenance role is not the backend
runtime role and is not the Telegram delivery-worker role.

One maintenance iteration runs at most the configured batch size against each
technical table. Defaults:

- expired or revoked `auth_sessions`: retain for 7 days;
- processed `telegram_updates`: retain for 30 days;
- terminal `notification_outbox` rows: retain for 90 days;
- callbacks belonging to terminal access decisions: retain for 30 days;
- batch limit: 1000 rows per target per iteration;
- worker interval: 3600 seconds.

The maintenance role has `SELECT, DELETE` only on the four technical targets
and read-only `SELECT` on `access_requests`, which is needed to determine
whether callback state is terminal.

`movements`, `movement_lines`, `stock_balances` and other warehouse state are
outside the retention target set. The canonical warehouse
movement journal remains immutable and is never pruned by this worker.

## Operational mutation gate

Initial production inventory уже загружен guarded one-shot bootstrap-процедурой.

Regular warehouse mutation endpoints независимо защищены:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Пока gate закрыт, normal ISSUE/RETURN/RECEIPT/TRANSFER/WRITE_OFF/CORRECTION/
REVERSAL API не переводится в operational go-live.

Gate может быть изменён только отдельным explicit production decision после:

- repository / VM / local hygiene;
- independent full audit;
- устранения blocking findings;
- запланированных minor UX corrections;
- fresh pre-change backup;
- production health/reconciliation verification.

Повторный initial bootstrap не является способом включения normal operations и
запрещён после первого успешного production load.
