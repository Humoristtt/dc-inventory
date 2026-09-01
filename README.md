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

В production развёрнуты runtime foundation и Stage 4 Telegram/access
foundation:

- Python 3.12 + FastAPI;
- SQLAlchemy 2 async + asyncpg;
- Alembic;
- PostgreSQL 18;
- React + TypeScript + Vite;
- Nginx как единая точка входа;
- production-shaped Docker Compose;
- `/api/health/live` и `/api/health/ready`;
- Telegram `initData` HMAC validation;
- server-side `HttpOnly` sessions;
- `ADMIN` / `USER` и access-state foundation;
- frontend access gate и запрос доступа;
- Telegram webhook с secret-token validation и persistent `update_id` dedupe;
- transactional notification outbox;
- отдельный `telegram-worker`;
- Cloudflare Worker Telegram Gateway;
- ADMIN approve/reject через inline-кнопки;
- Ruff, mypy strict, Pytest, Oxlint, TypeScript, Vitest;
- GitHub Actions CI;
- Cloudflare Tunnel для публикации Mini App.

Production runtime публикует на host только `127.0.0.1:8080`; backend и PostgreSQL доступны только внутри Docker-сетей.

Фактически проверено:

    DB UP   -> live 200 / ready 200
    DB DOWN -> live 200 / ready 503
    DB BACK -> live 200 / ready 200

Readiness восстанавливается после возврата PostgreSQL без рестарта backend.

Stage 4 Telegram/auth/access foundation закрыт production smoke 2026-09-01:
неизвестный пользователь запросил доступ, ADMIN получил Telegram-уведомление,
одобрил запрос inline-кнопкой, пользователь получил уведомление и вошёл в Mini App.

В текущем исходном коде реализован Stage 5 Catalog Foundation, но он ещё не
развёрнут в production:

- Category, Manufacturer и Item;
- metadata-driven CategoryAttribute и typed ItemAttributeValue;
- Approved read API и Admin mutation API;
- пять initial versioned schemas: SFP, оптика, кабели питания, NIC и диски;
- source-backed refinement: медные сетевые кабели, conductor attributes для
  кабелей питания и уточнённые SFP vocabularies.

Item является каталожной позицией; физические serial units относятся к будущему
InventoryUnit и в Stage 5 не реализованы. Три локальных workbook сверены только
как reference examples для catalog design. Refinement ожидает независимый
review/CI; Stage 6 не начат.

## Номенклатура

На старте система должна учитывать, в частности:

- SFP/SFP+/SFP28 и другие трансиверы;
- оптические кабели;
- медные кабели;
- силовые кабели;
- диски;
- сетевые карты;
- другие категории, которые будут добавляться позднее.

Исходные Excel-файлы используются только как reference material для границ
категорий, терминологии и технических атрибутов. Они не являются inventory
database или обязательным import source. Существующие количества/остатки не
импортируются; фактический stock проверяется владельцем вручную при вводе
оборудования. После запуска PostgreSQL остаётся единственным источником истины.

## Технологический стек

- Frontend: React + TypeScript + Vite
- Backend: FastAPI
- ORM: SQLAlchemy 2
- Миграции: Alembic
- База данных: PostgreSQL
- Telegram integration: FastAPI webhook + transactional outbox + delivery worker
- Контейнеризация: Docker Compose
- Reverse proxy: Nginx
- Публикация Mini App: Cloudflare Tunnel
- CI: GitHub Actions
- Backend tests: Pytest
- Frontend tests: Vitest
- E2E: Playwright — запланирован roadmap, не текущий runtime dependency

## Инфраструктура

Production VM:

- Ubuntu Server 24.04 LTS
- Docker Engine + Docker Compose
- SSH только по ключу
- серверное время UTC
- приложение публикуется через Cloudflare
- PostgreSQL не публикуется наружу

Прямой доступ production VM к `api.telegram.org` в текущей сети блокируется на TCP/443. Исходящие Bot API вызовы production выполняются через отдельный Cloudflare Worker Telegram Gateway; bot token не передаётся `telegram-worker`.

## Документация

Каноническая документация проекта находится в каталоге [`docs/`](docs/).

История проекта ведётся в [`docs/HISTORY.md`](docs/HISTORY.md).

Развёртывание:

[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
