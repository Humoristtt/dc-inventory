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

## Секреты

Production `.env` создаётся непосредственно на VM и не хранится в Git.

Для базового runtime необходимы:

    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    DATABASE_URL

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
`initData`. Frontend его никогда не получает.

Отдельный `telegram-worker` использует:

    TELEGRAM_GATEWAY_URL
    TELEGRAM_GATEWAY_SECRET
    TELEGRAM_GATEWAY_TIMEOUT_SECONDS
    NOTIFICATION_WORKER_POLL_SECONDS
    NOTIFICATION_WORKER_CLAIM_TTL_SECONDS
    NOTIFICATION_WORKER_BATCH_SIZE
    NOTIFICATION_WORKER_MAX_ATTEMPTS

`telegram-worker` не получает bot token, webhook secret или ADMIN ID.

Cloudflare Worker имеет собственные secrets:

    BOT_TOKEN
    GATEWAY_SECRET

Значение `GATEWAY_SECRET` является отдельным shared secret между production
worker и Cloudflare Worker. Секреты Cloudflare не хранятся в Git.

Migration container получает только DB-конфигурацию.

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

Cloudflare Gateway принимает Stage 4 allowlist:

    sendMessage
    editMessageText
    editMessageReplyMarkup
    answerCallbackQuery

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

Предметные миграции должны быть безопасны для последовательного deploy. Для потенциально разрушительных изменений обязателен backup и заранее определённый rollback/forward-fix plan.

## Проверка после deploy

    curl http://127.0.0.1:8080/healthz
    curl http://127.0.0.1:8080/api/health/live
    curl http://127.0.0.1:8080/api/health/ready

Ожидается HTTP 200 для всех трёх запросов.

Также проверяются:

- `postgres`, `backend`, `web` — healthy;
- `telegram-worker` — `Up`;
- `migrate` — `Exited (0)`;
- на host отсутствуют listen-порты `8000` и `5432`;
- backend работает от UID 10001;
- web работает от пользователя `nginx`;
- для runtime-changing deploy production worktree соответствует утверждённому deploy commit;
- docs-only sync может продвигать worktree вперёд без rebuild/restart контейнеров, если runtime source не менялся.

Для Telegram delivery после runtime-changing deploy выполняется минимальный live
smoke: `/start` должен пройти webhook/outbox/worker/Gateway и вернуться
сообщением в Telegram. Для access acceptance используется отдельный пользователь:
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
