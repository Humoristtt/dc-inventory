# Инвентаризация оборудования ЦОД

Внутреннее Telegram Mini App для учёта оборудования и расходных материалов ЦОД.

Система предназначена для контроля фактических складских остатков и полной истории движения оборудования: кто, когда, откуда, куда, что именно и в каком количестве получил, вернул, переместил, оприходовал или списал.

## Основные принципы

- PostgreSQL является каноническим источником данных.
- Остатки изменяются только через складские операции.
- История операций сохраняется и не переписывается задним числом.
- Warehouse Domain V2 использует только количественный учёт; legacy serial/custody model не является частью целевой схемы этой ветки.
- Поддерживается несколько складов и локаций.
- Каталог Warehouse V2 использует versioned fixed hierarchy и leaf schemas; изменения схем выполняются через код и миграции, а не runtime-конструктор.
- Доступ пользователей осуществляется через Telegram.
- Базовые роли: `ADMIN` и `USER`.
- Transactional Telegram notification infrastructure реализована; ISSUE создаёт deduplicated admin Telegram notification через outbox.
- Production разворачивается только из зафиксированного Git commit.
- Production VM имеет только read-only доступ к GitHub-репозиторию.

## Текущее состояние

В production приняты Stages 4–8B, branded Telegram `/start` flow и
post-8B UX foundations. Stage15A automated off-VM PostgreSQL backup и Stage15B
real isolated restore — `PASS`; Stage15 technical hardening завершён. Production-data gate намеренно остаётся закрытым до следующего roadmap.

AUD-01 fail-closed server-side real-inventory mutation gate принят в
production. Runtime остаётся заблокирован:

    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP

Текущий migration head — `a2b3c4d5e6f7`. Production Git checkout и реально
запущенные application images рассматриваются как разные operational facts;
Stage15 backup provenance фиксирует их отдельно.

Production runtime включает:

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
- отдельный least-privilege `maintenance-worker`;
- разделённые PostgreSQL identities для owner/migrations, backend runtime,
  Telegram worker и maintenance worker;
- bounded technical-data retention;
- Cloudflare Worker Telegram Gateway;
- branded Telegram `/start`: персональное приветствие, удаление команды,
  замена предыдущего welcome, image-card через `sendPhoto` и кнопка открытия
  Mini App;
- production gateway URL требует HTTPS;
- ADMIN approve/reject через inline-кнопки;
- Ruff, mypy strict, Pytest, Oxlint, TypeScript, Vitest;
- GitHub Actions CI;
- Cloudflare Tunnel для публикации Mini App.
- metadata-driven catalog API, global/category search и facets;
- глобальный поиск и scoped catalog facets;
- immutable warehouse journal, quantity balances по StorageLocation и
  projection reconciliation.

Production runtime публикует на host только `127.0.0.1:8080`; backend и PostgreSQL доступны только внутри Docker-сетей.

Фактически проверено:

    DB UP   -> live 200 / ready 200
    DB DOWN -> live 200 / ready 503
    DB BACK -> live 200 / ready 200

Readiness восстанавливается после возврата PostgreSQL без рестарта backend.

Stage 4 Telegram/auth/access foundation закрыт production smoke 2026-09-01:
неизвестный пользователь запросил доступ, ADMIN получил Telegram-уведомление,
одобрил запрос inline-кнопкой, пользователь получил уведомление и вошёл в Mini App.

Stage 5 Catalog Foundation и Stage 6 Warehouse Core входят в текущий
production baseline на migration head `a2b3c4d5e6f7`.

Warehouse Domain V2 этой feature-ветки является следующим schema/product
состоянием и не должен считаться уже развёрнутым в production до отдельного
merge/deploy acceptance. Целевая модель V2 включает:

- фиксированную versioned hierarchy каталога с leaf schemas;
- Category, Manufacturer и Item без physical-unit accounting mode;
- role-aware API: approved USER видит каталог, остатки и собственную actor-history,
  выполняет ISSUE/RETURN; ADMIN получает общий journal и administrative mutations;
- first-class StorageLocation типов WAREHOUSE / DATACENTER;
- append-only Movement/MovementLine journal: receipt, issue, return, transfer,
  write-off, correction и reversal;
- integer StockBalance projection только Item × StorageLocation;
- отсутствие personal custody, holder balances и InventoryUnit в активной V2 schema;
- PostgreSQL row/advisory locking, request idempotency, immutable-journal guards
  и concurrency regression tests;
- projection reconciliation из immutable movement journal;
- transactional admin Telegram notification на ISSUE;
- same-origin vendored Telegram Web App SDK с фиксированным SHA-256 и явным
  frontend failure state.

Stage 7 также завершён и развёрнут: реализованы и протестированы deterministic
sorting/pagination, global/category search, availability, location и
metadata-driven filters/facets.

Stage 8A Working Mini App Catalog UX завершён и принят в production:
application shell, API-driven categories, debounced global/category search,
metadata-driven facet filters, sorting, progressive item list, compact cards,
Item detail, URL-preserving navigation, Telegram BackButton/safe-area integration
и production viewport remediation работают на текущем baseline.

Stage 8B завершён и принят в production: metadata-driven Admin
create/edit/archive/unarchive, inline Manufacturer и duplicate-check UX,
stock-by-location detail, bounded facets, privacy/auth/runtime hardening и
production-Nginx Playwright acceptance
прошли local gate, PR #22 required CI и production smoke. Chromium и WebKit
покрывают mobile/browser acceptance. Production migration head — `a2b3c4d5e6f7`; exact runtime source
проверяется по image provenance, а не выводится только из Git checkout.

Item остаётся каталожной позицией, а не физическим экземпляром.
Warehouse V2 не содержит active SERIAL/WWN/InventoryUnit/current-holder semantics.

Для первоначального наполнения Warehouse V2 authoritative operator input —
внешний workbook `inventory.xlsx`. Он хранится вне репозитория и не должен
попадать в Git. Bootstrap импортирует его только в явно существующую активную
локацию, создаёт начальный RECEIPT и fail-closed отказывается от повторного
импорта в уже наполненный warehouse domain.

Stage15A/B уже доказали automated off-VM backup и real isolated restore,
но ввод real inventory остаётся заблокирован до полного Stage15C acceptance и
отдельного explicit operator action. Перед первым вводом снова выполняется
read-only projection reconciliation из
`backend/scripts/reconcile_inventory_projections.sql`.

## Номенклатура

На старте система должна учитывать, в частности:

- SFP/SFP+/SFP28 и другие трансиверы;
- оптические кабели;
- медные кабели;
- силовые кабели;
- диски;
- сетевые карты;
- другие категории, которые будут добавляться позднее.

Для bootstrap Warehouse V2 authoritative input — операторский `inventory.xlsx`,
расположенный вне репозитория. Его mapping зафиксирован в bootstrap-коде и
регрессионных тестах. Сам workbook, его копии и реальные складские данные
не должны коммититься в публичный репозиторий.

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
- Browser acceptance: Playwright с Telegram Desktop narrow, Android-like,
  iPhone-like, iPhone WebKit и desktop/admin profiles; API/Telegram boundaries
  в этом suite deterministic synthetic

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

Основные canonical документы:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PRODUCT_REQUIREMENTS.md`](docs/PRODUCT_REQUIREMENTS.md)
- [`docs/CATALOG_SCHEMA.md`](docs/CATALOG_SCHEMA.md)
- [`docs/WAREHOUSE_DOMAIN.md`](docs/WAREHOUSE_DOMAIN.md)
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/STAGE15_PLAN.md`](docs/STAGE15_PLAN.md)
- [`docs/STAGE15_AUDIT_REMEDIATION.md`](docs/STAGE15_AUDIT_REMEDIATION.md)
- [`docs/RECOVERY_RUNBOOK.md`](docs/RECOVERY_RUNBOOK.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
