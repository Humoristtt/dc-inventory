# Инвентаризация оборудования ЦОД

Внутреннее Telegram Mini App для учёта оборудования и расходных материалов ЦОД.

Система предназначена для контроля фактических складских остатков и полной истории движения оборудования: кто, когда, откуда, куда, что именно и в каком количестве получил, вернул, переместил, оприходовал или списал.

## Основные принципы

- PostgreSQL является каноническим источником данных.
- Остатки изменяются только через складские операции.
- История операций сохраняется и не переписывается задним числом.
- Поддерживается количественный и серийный учёт.
- Поддерживается несколько складов и локаций.
- Категории оборудования расширяемы без переделки всей системы.
- Доступ пользователей осуществляется через Telegram.
- Базовые роли: `ADMIN` и `USER`.
- Администратор получает уведомления о выдаче оборудования.
- Production разворачивается только из зафиксированного Git commit.
- Production VM имеет только read-only доступ к GitHub-репозиторию.

## Текущее состояние

Реализован backend runtime foundation:

- Python 3.12;
- FastAPI;
- SQLAlchemy 2 в async-режиме;
- asyncpg;
- Alembic;
- PostgreSQL 18 для локальной разработки;
- `/api/health/live`;
- `/api/health/ready`;
- Ruff;
- mypy в strict-режиме;
- Pytest;
- development Docker Compose для PostgreSQL.

Фактически проверено:

    DB UP   -> live 200 / ready 200
    DB DOWN -> live 200 / ready 503
    DB BACK -> live 200 / ready 200

Readiness восстанавливается после возврата PostgreSQL без рестарта backend.

## Номенклатура

На старте система должна учитывать, в частности:

- SFP/SFP+/SFP28 и другие трансиверы;
- оптические кабели;
- медные кабели;
- силовые кабели;
- диски;
- сетевые карты;
- другие категории, которые будут добавляться позднее.

Исходные Excel-файлы используются только для первичного импорта и сверки. После запуска приложения они не являются источником истины.

## Технологический стек

- Frontend: React + TypeScript + Vite
- Backend: FastAPI
- ORM: SQLAlchemy 2
- Миграции: Alembic
- База данных: PostgreSQL
- Telegram Bot: aiogram
- Контейнеризация: Docker Compose
- Reverse proxy: Nginx
- Публикация Mini App: Cloudflare Tunnel
- CI: GitHub Actions
- Backend tests: Pytest
- Frontend tests: Vitest
- E2E: Playwright

## Инфраструктура

Production VM:

- Ubuntu Server 24.04 LTS
- Docker Engine + Docker Compose
- SSH только по ключу
- серверное время UTC
- приложение публикуется через Cloudflare
- PostgreSQL не публикуется наружу

Прямой доступ production VM к `api.telegram.org` в текущей сети блокируется на TCP/443. Для Telegram Bot API будет предусмотрен отдельный безопасный gateway через Cloudflare.

## Документация

Каноническая документация проекта находится в каталоге [`docs/`](docs/).

История проекта ведётся в [`docs/HISTORY.md`](docs/HISTORY.md).

Развёртывание:

[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
