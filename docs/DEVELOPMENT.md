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

## Конфигурация

Пример конфигурации находится в `.env.example`.

Локальная разработка использует `.env` в корне репозитория. Файл содержит локальные секреты и исключён из Git.

Реальные пароли, токены и production URLs коммитить запрещено.

## PostgreSQL

Для локальной разработки PostgreSQL запускается через:

    docker compose --env-file .env -f compose.dev.yaml up -d --wait postgres

Development-порт публикуется только на loopback:

    127.0.0.1:55432

## Alembic

При запуске Alembic с development-машины используется host-порт PostgreSQL:

    set -a
    source .env
    set +a

    HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"

    cd backend
    DATABASE_URL="$HOST_DATABASE_URL" alembic upgrade head

Текущий baseline Alembic:

    48c2f07f01a0

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
