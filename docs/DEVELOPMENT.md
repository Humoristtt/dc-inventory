# Локальная разработка

## Требования

Для текущего проекта необходимы:

- Python 3.12;
- Node.js 24;
- Docker Engine;
- Docker Compose.

## Backend environment

Рабочее окружение backend создаётся в каталоге `backend`:

    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --require-hashes -r requirements-dev.lock

`.venv` является локальным development-окружением и не хранится в Git.

`requirements-dev.lock` является воспроизводимым набором зависимостей для локальных проверок и CI. После изменения зависимостей в `pyproject.toml` lock-файл должен быть пересобран через `pip-compile` и проверен чистой установкой с `--require-hashes`.

## Frontend environment

Frontend использует Node.js 24:

    cd frontend
    npm ci

Основные команды:

    npm run dev
    npm run lint
    npm run typecheck
    npm test
    npm run build
    npx playwright install chromium webkit
    npm run test:e2e

## Конфигурация

Пример конфигурации находится в `.env.example`.

Локальная разработка использует `.env` в корне репозитория. Файл содержит локальные секреты и исключён из Git.

Реальные пароли, токены и production URLs коммитить запрещено.

## PostgreSQL

Для локальной разработки PostgreSQL запускается через:

    docker compose --env-file .env -f compose.dev.yaml up -d --wait postgres

Development-порт публикуется только на loopback:

    127.0.0.1:55432

Для этого `postgres` дополнительно подключён к development-only
`dev_host_net`. Основной backend-доступ к БД по-прежнему идёт через
внутреннюю `db_net`; `web` к сети публикации PostgreSQL не подключён.

## Alembic

При запуске Alembic с development-машины используется host-порт PostgreSQL:

    set -a
    source .env
    set +a

    HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"

    cd backend
    DATABASE_URL="$HOST_DATABASE_URL" alembic upgrade head

Baseline Alembic:

    48c2f07f01a0

Текущий source migration head:

    f8a9b0c1d2e3

Production migration head на текущем принятом production baseline:

    c5d6e7f8a9b0

Source head и production head не следует смешивать: новый source migration head
считается production state только после отдельного deploy/migration acceptance.

## Локальный backend

    set -a
    source .env
    set +a

    HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"

    cd backend
    DATABASE_URL="$HOST_DATABASE_URL" APP_ENV=development uvicorn app.main:app --host 127.0.0.1 --port 8000

Endpoints:

    GET http://127.0.0.1:8000/api/health/live
    GET http://127.0.0.1:8000/api/health/ready

Swagger/OpenAPI доступны только вне production:

    http://127.0.0.1:8000/api/docs

## Единый development runtime

Полный стек запускается из корня:

    docker compose --env-file .env -f compose.dev.yaml up -d --build --wait web

Единая точка входа:

    http://127.0.0.1:8080

Backend и PostgreSQL остаются разделены отдельной внутренней DB-сетью; frontend/Nginx не имеет прямого доступа к PostgreSQL.

## Проверки

Backend:

    cd backend
    ruff check app tests migrations
    mypy app tests migrations/env.py migrations/versions
    pytest -q

Frontend:

    cd frontend
    npm run lint
    npm run typecheck
    npm test
    npm run build
    npm run test:e2e

Текущий frontend включает Warehouse Domain V2 catalog/Admin/stock/movement UX
поверх существующего Telegram/auth/access gate. Отдельного active «Моё
оборудование» UI сейчас нет; custody является backend integrity projection.
Focused Vitest regressions
находятся рядом с components/pages. `frontend/e2e/warehouse-v2.spec.ts`
использует deterministic synthetic API/Telegram boundaries и запускается на
Telegram Desktop narrow, Android-like, iPhone-like и desktop profiles. Это
browser-level acceptance, а не full-stack E2E: FastAPI/PostgreSQL этим
Playwright suite не поднимаются; backend contracts проверяются отдельными
Pytest/integration suites. Browser runtime устанавливается локально через
`npx playwright install chromium webkit`; CI устанавливает browser dependencies
в required browser gate.

Из корня репозитория:

    git diff --check

Полный набор проверок выполняется на границе логического change set, а не после каждого небольшого редактирования.

## Health-check acceptance

Проверенный lifecycle:

    PostgreSQL UP:
      /live  -> 200
      /ready -> 200

    PostgreSQL DOWN:
      /live  -> 200
      /ready -> 503

    PostgreSQL BACK:
      /live  -> 200
      /ready -> 200

Backend восстанавливает readiness после кратковременной потери PostgreSQL без собственного рестарта.

## Git workflow

Production VM не используется как development-машина.

Путь изменений:

    Mac
      -> GitHub
      -> проверенный commit/main
      -> production VM

Production VM имеет read-only GitHub Deploy Key.

Runtime-changing application images обязаны получать source revision:

    APP_REVISION="$(git rev-parse HEAD)" docker compose build backend web

Dockerfiles сохраняют его в OCI label
`org.opencontainers.image.revision`.

Production Git checkout не используется как замена runtime image provenance.

## Telegram authentication в development

Для реального Telegram login backend нужны `TELEGRAM_BOT_TOKEN` и числовой
`ADMIN_TELEGRAM_USER_ID` из локального `.env`. Bot token никогда не передаётся
frontend.

`POSTGRES_DEV_PORT` позволяет поднять изолированную test DB на другом
loopback-порту, например `55433`.

## PostgreSQL integration tests

Обычный локальный `pytest` пропускает PostgreSQL integration tests. Полный
gate запускает их явно против уже мигрированной PostgreSQL 18:

    RUN_POSTGRES_INTEGRATION=1     DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:PORT/dc_inventory     pytest -q

CI всегда включает этот режим.

Отдельный migration-safety gate проверяет destructive downgrade SFP metadata
на реальном PostgreSQL 18. Обычный `pytest` этот сценарий пропускает; локальный
эквивалент required backend CI запускается явно:

    RUN_SFP_DOWNGRADE_POSTGRES=1 \
    DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:PORT/dc_inventory \
    pytest -q tests/test_sfp_migration_downgrade_postgres.py

Этот regression обязан доказать как успешный безопасный downgrade/upgrade cycle
без profile values, так и отказ downgrade при существующих SFP profile values
без потери данных и без смещения Alembic revision с `head`.

Catalog PostgreSQL checks можно запускать сфокусированно:

    RUN_POSTGRES_INTEGRATION=1 \
    DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:PORT/dc_inventory \
    pytest -q tests/test_catalog_postgres.py tests/test_catalog_api_postgres.py

Warehouse PostgreSQL checks, включая quantity allocation, concurrent
movements, idempotency, correction/reversal и API authorization:

    RUN_POSTGRES_INTEGRATION=1 \
    DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:PORT/dc_inventory \
    pytest -q tests/test_inventory_postgres.py tests/test_inventory_api_postgres.py

## Production-role integration regressions

Полный PostgreSQL gate проверяет не только owner-level domain tests, но и
production least-privilege identities.

Обязательные regressions:

- backend может `INSERT telegram_updates` и обновить только `processed_at`;
- backend не имеет broad UPDATE immutable warehouse journal;
- correction/reversal выполняются без UPDATE privilege на `Movement`;
- journal sequence access ограничен требуемой identity sequence;
- controlled `DEAD -> PENDING` access-notification recovery работает под
  runtime-role;
- notification payload backend-role изменять не может;
- maintenance worker выполняет реальную bounded retention iteration.

## Browser acceptance

Есть два независимых browser-level слоя проверки.

`npm run test:e2e` запускает Warehouse V2 UX/browser acceptance из
`frontend/e2e/warehouse-v2.spec.ts` с синтетическими API fixtures. Этот слой
нужен для deterministic UI, responsive и Telegram-shell сценариев.

`npm run test:e2e:fullstack` запускается CI против production-shaped
`compose.yaml`: настоящий frontend nginx проксирует запросы в настоящий FastAPI,
который работает с PostgreSQL. В тесте синтетически задаётся только Telegram
WebApp context с корректно подписанным CI `initData`; `/api/*` routes не
мокаются. CI дополнительно подтверждает созданные Telegram identity/auth session
непосредственно в PostgreSQL и проверяет, что warehouse tables остались пустыми.

## Warehouse projection reconciliation

Warehouse Domain V2 содержит read-only projection reconciliation без
repair/rebuild framework. Проверка обязательна после warehouse migrations,
после restore, при controlled bootstrap/data migration и при подозрении на
projection drift. Для локального development runtime запустить из корня
репозитория:

    set -a
    source .env
    set +a

    PSQL_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_DEV_PORT:-55432}/${POSTGRES_DB}"
    psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 \
      -f backend/scripts/reconcile_inventory_projections.sql

Скрипт пересчитывает quantity-by-location и quantity-by-user custody projections
из immutable Movement/MovementLine journal. Result set должен содержать zero rows. Любая
строка означает data-integrity blocker: остановить inventory mutations,
сохранить backup artifact и расследовать причину; скрипт сам ничего не чинит.
Warehouse V2 не имеет active InventoryUnit/serial projection; custody хранится
отдельной агрегированной User × Item projection.

Stage15A automated backup, Stage15B real isolated restore и Stage15
technical hardening приняты.

Initial production inventory bootstrap выполнен отдельным guarded one-shot path.
Regular API mutations остаются независимо защищены
`REAL_INVENTORY_MUTATIONS_ENABLED=false` до отдельного operational go-live
decision.

## Checkpoint и source audit

Рабочий цикл для логического change set:

    CODE
      -> focused local checks
      -> commit / push
      -> GitHub PR + CI
      -> source audit
      -> merge
      -> production deploy / smoke при необходимости

Репозиторий доступен для прямого source review через GitHub, поэтому архив
исходников не является обязательным checkpoint. Архив создаётся только когда
он действительно нужен для конкретного независимого анализа.

Полный gate не запускается после каждого мелкого редактирования: он выполняется
на границе логического change set. Документация и roadmap обновляются вместе
с фактическим состоянием реализации.
