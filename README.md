# Инвентаризация оборудования ЦОД

Внутреннее Telegram Mini App для учёта оборудования и расходных материалов ЦОД.

Система предназначена для контроля фактических складских остатков и полной истории движения оборудования: кто, когда, откуда, куда, что именно и в каком количестве получил, вернул, переместил, оприходовал или списал.

## Основные принципы

- PostgreSQL является каноническим источником данных.
- Остатки изменяются только через складские операции.
- История операций сохраняется и не переписывается задним числом.
- Warehouse Domain V2 использует количественный учёт без physical-unit/serial lifecycle.
- Текущие транзакционные проекции: `StockBalance` = Item × Location и `UserItemCustodyBalance` = User × Item.
- USER ISSUE/RETURN изменяют персональную custody-проекцию; ADMIN warehouse movements не создают custody.
- Поддерживается несколько складов и локаций.
- Каталог Warehouse V2 использует versioned fixed hierarchy и leaf schemas; изменения схем выполняются через код и миграции, а не runtime-конструктор.
- Доступ пользователей осуществляется через Telegram.
- Базовые роли: `ADMIN` и `USER`.
- Transactional Telegram notification infrastructure реализована; ISSUE создаёт deduplicated admin Telegram notification через outbox.
- Production разворачивается только из зафиксированного Git commit.
- Production VM имеет только read-only доступ к GitHub-репозиторию.

## Текущее состояние

Warehouse Domain V2 развёрнут и принят в production.

Текущий production schema baseline:

    ALEMBIC_HEAD=c5d6e7f8a9b0

Текущий source migration head:

    SOURCE_ALEMBIC_HEAD=f8a9b0c1d2e3

Production migration state и source migration head являются разными operational
facts до отдельного deploy/migration acceptance.

Stage 15 technical hardening завершён. Automated off-VM PostgreSQL backup,
isolated restore rehearsal, runtime provenance, least-privilege DB identities,
security/runtime CI и recovery procedure приняты.

Первоначальное production-наполнение склада также завершено:

- authoritative operator workbook хранится вне Git;
- workbook прошёл fail-closed validation;
- production bootstrap выполнен отдельным guarded one-shot CLI;
- bootstrap создал одну initial RECEIPT transaction;
- post-bootstrap stock/journal reconciliation вернул zero drift;
- production health после bootstrap — PASS;
- fresh verified off-VM backup после bootstrap — PASS;
- Telegram Mini App visual acceptance после загрузки данных — PASS.

Реальные inventory datasets, workbook contents, production identifiers и
операционные source artifacts в repository не помещаются.

Обычный warehouse mutation API по-прежнему защищён fail-closed boundary:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Это не означает, что production inventory отсутствует. Initial bootstrap уже
выполнен через отдельный one-shot production bootstrap path, который специально
требует закрытый regular mutation gate и отказывается работать с уже наполненным
warehouse domain.

Повторный initial bootstrap запрещён.

Следующая operational фаза перед обычным warehouse go-live:

    documentation closeout
      -> repository / VM / local hygiene
      -> independent full audit
      -> minor UX remediation
      -> final acceptance
      -> explicit regular-mutation gate decision

Production Git checkout и revision реально запущенных application images
являются отдельными operational facts. Exact runtime provenance проверяется по
OCI label `org.opencontainers.image.revision` и backup manifest, а не выводится
только из текущего Git checkout.

Production runtime включает:

- Python 3.12 + FastAPI;
- SQLAlchemy 2 async + asyncpg;
- Alembic;
- PostgreSQL 18;
- React + TypeScript + Vite;
- Nginx как единую точку входа;
- production-shaped Docker Compose;
- `/api/health/live` и `/api/health/ready`;
- Telegram `initData` HMAC validation;
- server-side `HttpOnly` sessions;
- `ADMIN` / `USER` access model;
- Telegram webhook с persistent `update_id` dedupe;
- transactional notification outbox;
- отдельный `telegram-worker`;
- отдельный least-privilege `maintenance-worker`;
- разделённые PostgreSQL identities для owner/migrations, backend runtime,
  Telegram worker и maintenance worker;
- bounded technical-data retention;
- Cloudflare Worker Telegram Gateway;
- branded Telegram `/start`;
- Cloudflare Tunnel;
- fixed Warehouse V2 catalog hierarchy;
- scoped search/facets;
- immutable warehouse movement journal;
- quantity-only `StockBalance`;
- quantity-only `UserItemCustodyBalance`;
- custody-aware USER ISSUE/RETURN;
- read-only stock + custody projection reconciliation;
- responsive Telegram/mobile/desktop Warehouse UI;
- guarded external-workbook initial bootstrap.

Production runtime публикует на host только `127.0.0.1:8080`; backend и
PostgreSQL доступны только внутри Docker-сетей.

Item является номенклатурной позицией, а не физическим экземпляром.
Warehouse V2 не содержит active serial/WWN physical-unit lifecycle.
Персональная ответственность за выданное USER оборудование хранится отдельно
как агрегированная количественная custody-проекция User × Item; это не модель
индивидуальных physical units.

## Номенклатура

Текущая Warehouse V2 hierarchy покрывает:

- Ethernet и Fibre Channel трансиверы;
- оптические патч-корды;
- оптические сплиттеры и делители;
- Ethernet и Fibre Channel сетевые адаптеры;
- SSD;
- HDD;
- оперативную память;
- PCIe-адаптеры;
- кабели питания.

Технические поля определяются leaf category schema.

Authoritative input первоначального production bootstrap — внешний операторский
`inventory.xlsx`. Workbook и его реальные значения находятся вне repository.
Mapping и validation contract зафиксированы в bootstrap-коде и regression tests.

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
