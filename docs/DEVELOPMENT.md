# Локальная разработка

## Требования

Для текущего backend необходимы:

- Python 3.12;
- Docker Engine;
- Docker Compose.

Frontend пока не реализован.

## Python environment

Рабочее окружение backend создаётся в каталоге `backend`:

    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -e '.[dev]'

`.venv` является локальным development-окружением и не хранится в Git.

## Конфигурация

Пример конфигурации находится в `.env.example`.

Локальная разработка использует `.env` в корне репозитория.

`.env` содержит локальные секреты и исключён из Git.

Реальные пароли, токены и production URLs коммитить запрещено.

## PostgreSQL

Для локальной разработки PostgreSQL запускается через:

    docker compose --env-file .env -f compose.dev.yaml up -d --wait postgres

Проверить состояние контейнера можно через:

    docker compose --env-file .env -f compose.dev.yaml ps

PostgreSQL должен перейти в состояние `healthy`.

Development-порт публикуется только на loopback:

    127.0.0.1:55432

## Alembic

При запуске Alembic с development-машины используется host-порт PostgreSQL.

Пример:

    set -a
    source .env
    set +a

    HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"

    cd backend
    DATABASE_URL="$HOST_DATABASE_URL" alembic upgrade head

Текущий baseline Alembic:

    48c2f07f01a0

## Локальный запуск backend

Из корня репозитория:

    set -a
    source .env
    set +a

    HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"

    cd backend

    DATABASE_URL="$HOST_DATABASE_URL" APP_ENV=development       uvicorn app.main:app --host 127.0.0.1 --port 8000

Endpoints:

    GET http://127.0.0.1:8000/api/health/live
    GET http://127.0.0.1:8000/api/health/ready

OpenAPI:

    http://127.0.0.1:8000/api/docs

## Проверки backend

Перед фиксацией законченного change set выполняются:

    ruff check app tests migrations
    mypy app tests migrations/env.py migrations/versions
    pytest -q

Из корня репозитория дополнительно:

    git diff --check

Не требуется выполнять полный набор проверок после каждого небольшого редактирования файла. Проверки выполняются на границе логического этапа.

## Health-check acceptance

Фактически проверено:

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
