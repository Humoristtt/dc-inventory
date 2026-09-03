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
    npx playwright install chromium
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

    a2b3c4d5e6f7

Production остаётся на `f1a2b3c4d5e6` до Stage 8B release.

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

Текущий frontend включает Stage 8 catalog/Admin/stock/«Моё» UX поверх
существующего Telegram/auth/access gate. Focused Vitest regressions находятся
рядом с components/pages. `frontend/e2e/stage8.spec.ts` использует только
deterministic synthetic API/Telegram boundaries и запускается на Telegram
Desktop narrow, Android-like, iPhone-like и desktop/admin profiles. Browser
runtime устанавливается локально через `npx playwright install chromium`; CI
использует `--with-deps`.

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

Catalog PostgreSQL checks можно запускать сфокусированно:

    RUN_POSTGRES_INTEGRATION=1 \
    DATABASE_URL=postgresql+asyncpg://...@127.0.0.1:PORT/dc_inventory \
    pytest -q tests/test_catalog_postgres.py tests/test_catalog_api_postgres.py

Warehouse PostgreSQL checks, включая allocation и reactivation/reversal races:

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

## Warehouse projection reconciliation

Stage 6 содержит небольшой read-only drift check без repair/rebuild framework.
После migrations, перед первым реальным inventory вводом и после любого restore
запустить из корня репозитория:

    set -a
    source .env
    set +a

    PSQL_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_DEV_PORT:-55432}/${POSTGRES_DB}"
    psql "$PSQL_DATABASE_URL" -v ON_ERROR_STOP=1 \
      -f backend/scripts/reconcile_inventory_projections.sql

Скрипт пересчитывает quantity positions и latest serial state из immutable
Movement/MovementLine journal. Оба result set должны содержать zero rows. Любая
строка означает data-integrity blocker: остановить inventory mutations,
сохранить backup artifact и расследовать причину; скрипт сам ничего не чинит.

Это не снимает production-data gate. Реальные inventory данные запрещено
вводить, пока PostgreSQL automated backup не реализован и реальный restore этого
artifact не прошёл в отдельном окружении. Stage 6 deployment сам по себе не
разрешает production stock entry.

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
