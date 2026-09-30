# Spikatel Inventory

Spikatel Inventory — внутреннее приложение для количественного учёта оборудования и материалов ЦОД. Оно объединяет каталог номенклатуры, складские остатки, персональную custody, неизменяемый журнал движений, заявки на закупку, управление доступом и уведомления Telegram.

Этот репозиторий описывается только через **текущее состояние кода**. Исторические этапы, старые remediation-планы и прежние production SHA не являются частью нормативной документации.

## Что система учитывает

Система отвечает на четыре основных вопроса:

1. какая номенклатура существует;
2. сколько единиц каждой позиции находится в каждой StorageLocation;
3. сколько единиц закреплено за конкретным сотрудником;
4. какими неизменяемыми движениями получено текущее состояние.

`Item` — номенклатурная позиция, а не отдельный серийный экземпляр. Serial/WWN-level CMDB в текущий продукт не входит.

Основные предметные области:

- **Catalog** — категории, производители, технические атрибуты и identity позиции;
- **Warehouse** — места хранения, движения, stock projection и custody projection;
- **Procurement** — согласование закупки, immutable revisions/events и техническая приёмка;
- **Identity / Access** — Telegram identity, серверные сессии, статусы доступа, роли и capabilities;
- **Notifications** — transactional outbox для Telegram и optional Microsoft Graph email;
- **Maintenance** — ограниченное удаление только технических данных по retention policy.

## Архитектура в одном экране

```text
Telegram Mini App / браузер
        │ HTTPS
        ▼
host Nginx
        │ Unix socket в production
        ▼
web Nginx ───────────────► статический React/Vite frontend
        │ /api/*
        ▼
FastAPI
        │
        ├── auth / access / identity
        ├── catalog
        ├── inventory
        ├── procurement
        ├── telegram webhook
        └── health
        │
        ▼
PostgreSQL 18
        │
        ├── предметные таблицы и DB invariants
        ├── immutable journals/events
        └── transactional outbox
                │
                ├── Telegram worker ─► Cloudflare Gateway ─► Telegram Bot API
                └── Email worker ────► Microsoft Graph
```

Входящий Telegram webhook идёт отдельным маршрутом через Cloudflare Tunnel к FastAPI. Пользовательский web ingress и исходящая Telegram-доставка — разные границы.

Подробная схема: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Ключевые инварианты

- PostgreSQL — каноническое хранилище.
- Складской журнал `movements/movement_lines` не редактируется задним числом.
- `stock_balances` и `user_item_custody_balances` — производные проекции, а не независимый источник истины.
- Catalog identity защищена нормализацией, signature и PostgreSQL-trigger invariants.
- Procurement revisions/events и line bindings защищены от обычного изменения после публикации.
- Финальная приёмка Procurement создаёт Warehouse RECEIPT в той же транзакции.
- Backend проверяет capabilities; скрытие элементов frontend не является контролем доступа.
- Изменения role/access сопровождаются immutable audit events.
- Штатные inventory/catalog mutations дополнительно закрыты флагом `REAL_INVENTORY_MUTATIONS_ENABLED`, default — `false`.
- Email delivery default — `EMAIL_DELIVERY_ENABLED=false`.
- Внешняя доставка Telegram/email имеет семантику **at-least-once**, а не exactly-once.
- Runtime database identities разделены по назначению и получают least-privilege grants.
- Release связывает Git SHA с immutable Docker image IDs и OCI revision labels.
- Backup содержит provenance, Alembic head, SHA-256 и versioned S3 object IDs.

## Роли

Серверная политика использует пять ролей:

| Роль | Основное назначение |
|---|---|
| `ENGINEER` | чтение каталога, базовые складские операции, собственная история движений |
| `SENIOR_ENGINEER` | инженер + управление каталогом, общий журнал, техническая приёмка закупки |
| `MANAGER` | работа с процессом закупок |
| `ADMIN` | каталог, складские административные операции, создание закупок, управление пользователями |
| `OWNER` | ADMIN + назначение ADMIN; singleton recovery identity |

Точная capability-матрица и ограничения изменения ролей: [docs/ACCESS_AND_RBAC.md](docs/ACCESS_AND_RBAC.md).

## Текущий проверенный source baseline

Чистый аудит выполнен по `main`:

```text
SOURCE_SHA=2ba1fa1b1ca60bbbe4f75bf40e41f826581222c3
SOURCE_DATE=2026-09-30
ALEMBIC_HEAD=e3f4a5b6c7d8
```

На этом SHA GitHub CI завершён успешно:

- backend: Ruff PASS, mypy PASS для 212 source files, migration check PASS, `648 passed, 1 skipped`;
- frontend: lint/typecheck/build PASS, `165 passed` unit tests;
- browser acceptance: `142 passed, 12 skipped`;
- production-shaped full-stack: `2 passed` + проверка фактических DB side effects;
- Telegram Gateway: `7 passed`;
- runtime provenance и least-privilege DB checks: PASS;
- Trivy repository/image HIGH+CRITICAL gates: PASS.

Это **source/CI evidence**, а не утверждение о текущем live production. Фактическое состояние production проверяется только runtime-командами из [docs/OPERATIONS.md](docs/OPERATIONS.md).

Полный результат аудита и открытые технические риски: [docs/CURRENT_STATE_AUDIT.md](docs/CURRENT_STATE_AUDIT.md).

## Документация

Начальная карта: [docs/README.md](docs/README.md).

Основные документы:

- [ARCHITECTURE](docs/ARCHITECTURE.md) — компоненты, сети, доверие и пути взаимодействия;
- [PRODUCT_REQUIREMENTS](docs/PRODUCT_REQUIREMENTS.md) — фактический продуктовый контракт;
- [ACCESS_AND_RBAC](docs/ACCESS_AND_RBAC.md) — auth, access, roles и capabilities;
- [CATALOG](docs/CATALOG.md) — схема и identity каталога;
- [WAREHOUSE](docs/WAREHOUSE.md) — складской журнал, stock/custody и блокировки;
- [PROCUREMENT](docs/PROCUREMENT.md) — lifecycle закупки и связь со складом;
- [NOTIFICATIONS](docs/NOTIFICATIONS.md) — outbox, Telegram и email;
- [FRONTEND](docs/FRONTEND.md) — frontend architecture, navigation и design system;
- [SECURITY](docs/SECURITY.md) — trust boundaries, secrets, DB privileges и supply chain;
- [DEVELOPMENT](docs/DEVELOPMENT.md) — локальная разработка и проверки;
- [DEPLOYMENT](docs/DEPLOYMENT.md) — controlled release/deploy;
- [OPERATIONS](docs/OPERATIONS.md) — эксплуатация и runtime verification;
- [RECOVERY_RUNBOOK](docs/RECOVERY_RUNBOOK.md) — backup restore rehearsal и cutover boundary.

## Данные и секреты

Репозиторий публичный. В Git не должны попадать реальные `.env`, токены, пароли, private keys, дампы БД, production inventory datasets и **private/runtime-only production identifiers**.

**Публичные service identifiers** — например публичный hostname приложения — допустимы, если они необходимы для конфигурации и документации. Политика подробно описана в [docs/SECURITY.md](docs/SECURITY.md).
