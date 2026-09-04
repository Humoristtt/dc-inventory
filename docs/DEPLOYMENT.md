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

Текущий accepted production source:

    9a9ec6a705473d8bd3521b01e6f602284ed9c375

Текущий Alembic head:

    a2b3c4d5e6f7

Stage 15 preparation активна. До снятия production-data gate real inventory
entry запрещён; backup/restore acceptance описан в `docs/STAGE15_PLAN.md`.

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

Uvicorn доверяет proxy headers, потому что production backend не публикуется на host и доступен только через внутреннюю application-сеть.

Nginx применяет rate limiting после нормализации `CF-Connecting-IP`: общий API ограничен до 30 запросов/с на клиента с burst 60; `POST /api/auth/telegram` и `POST /api/access-requests` дополнительно ограничены до 10 запросов/мин с burst 5. Telegram webhook вынесен в отдельный лимит 50 запросов/с с burst 100, чтобы Telegram delivery burst не конкурировал с пользовательским API. Превышение ingress-лимита возвращает HTTP `429`.

## Supply-chain pinning

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
    SUPPORT_TELEGRAM_USERNAME
    AUTH_SESSION_TTL_SECONDS
    AUTH_COOKIE_NAME
    TELEGRAM_WEBHOOK_SECRET
    TELEGRAM_WEB_APP_URL

`TELEGRAM_BOT_TOKEN` нужен backend для server-side HMAC-проверки Telegram
`initData`. Это тот же Telegram-issued credential, который Cloudflare Worker
хранит независимо как secret `BOT_TOKEN` для Bot API. Frontend его никогда не
получает.

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

На чистой БД bootstrap ADMIN должен хотя бы один раз открыть Mini App и пройти
Telegram authentication до первого approve/reject callback: auth flow создаёт
`TelegramIdentity`, по которой callback подтверждает ADMIN identity.

## Миграции

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
- docs-only sync может продвигать worktree вперёд без rebuild/restart контейнеров, если runtime source не менялся.

Для Telegram delivery после runtime-changing deploy выполняется минимальный live
smoke: `/start` должен пройти webhook/outbox/worker/Gateway, удалить входящую
команду best-effort и вернуть branded `sendPhoto` welcome с caption и WebApp
button. Same-origin asset `/telegram/start-welcome.png` должен публично
отдаваться через production web path.

Для access acceptance используется отдельный пользователь:
request → ADMIN approve → user notification → вход в Mini App.

## Backup

До загрузки первых канонических складских данных должен быть реализован PostgreSQL backup/restore runbook и выполнен хотя бы один тест восстановления.
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

`movements`, `movement_lines`, `inventory_units`, `stock_balances` and other
warehouse state are outside the retention target set. The canonical warehouse
movement journal remains immutable and is never pruned by this worker.

## Production-data gate

Deploy Stage 5/6 сам по себе не разрешает ввод реальных inventory данных.

До первого production stock entry обязательны:

1. automated PostgreSQL backup;
2. проверяемый backup artifact вне production VM;
3. real restore test в отдельное окружение;
4. Alembic/schema verification после restore;
5. read-only projection reconciliation;
6. zero drift для QUANTITY и SERIAL.

Operational procedure находится в `docs/OPERATIONS.md`.
