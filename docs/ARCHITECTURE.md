# Архитектура Spikatel Inventory

Spikatel Inventory — модульный монолит: один FastAPI backend содержит предметную логику, PostgreSQL является каноническим хранилищем, React/Vite отвечает за интерфейс, а отдельные workers выполняют внешнюю доставку и retention.

Документ описывает **текущую архитектуру и пути взаимодействия**. Команды разработчика находятся в [DEVELOPMENT.md](DEVELOPMENT.md), deployment — в [DEPLOYMENT.md](DEPLOYMENT.md), эксплуатация — в [OPERATIONS.md](OPERATIONS.md).

## 1. Компоненты

```text
┌───────────────────────────┐
│ Telegram Mini App/browser │
└─────────────┬─────────────┘
              │ HTTPS
              ▼
┌───────────────────────────┐
│ host Nginx                │
│ TLS + host allowlist      │
└─────────────┬─────────────┘
              │ Unix socket
              ▼
┌───────────────────────────┐
│ web Nginx                 │
│ React static + /api proxy │
│ rate limits + headers     │
└─────────────┬─────────────┘
              │ internal app_net
              ▼
┌───────────────────────────┐
│ FastAPI backend           │
│ auth/access/catalog/etc.  │
└─────────────┬─────────────┘
              │ internal db_net
              ▼
┌───────────────────────────┐
│ PostgreSQL 18             │
│ canonical data + outbox   │
└───────┬──────────┬────────┘
        │          │
        │          └── maintenance worker (db_net only)
        │
        ├── telegram worker (db_net + egress_net)
        │          └── HTTPS Cloudflare Gateway ─► Telegram Bot API
        │
        └── email worker, optional (db_net + egress_net)
                   └── HTTPS Microsoft Graph
```

Отдельно:

```text
Telegram Bot API
   │ webhook
   ▼
telegram-webhook public hostname
   │ Cloudflare Tunnel
   ▼
host/web ingress
   │
   ▼
POST /api/telegram/webhook
```

Cloudflare Gateway для **исходящей** Telegram-доставки и Cloudflare Tunnel для **входящего** webhook — разные компоненты.


### Backend module boundaries

Backend остаётся модульным монолитом, но публичные service/query modules не содержат всю реализацию в одном файле.

- Catalog: `service.py` — façade; mutations — `mutations.py`; reads — `read_service.py`; item validation — `item_validation.py`; records — `records.py`. Query path разделён на `query_spec.py`, `query_predicates.py`, `query_items.py`, `query_facets.py`, `query_search.py` и `query_types.py`.
- Inventory: `service.py` — façade; movement mutations — `movements.py`; location mutations — `locations.py`; read paths — `queries.py`; low-level movement/idempotency support — `movement_support.py`; domain records/errors — `domain.py`.
- Procurement: `service.py` — façade; lifecycle — `workflow.py`; technical acceptance/binding — `acceptance.py`; reads — `queries.py`; line preparation — `lines.py`; locking/idempotency/state validation — `mutation_support.py`; actors/actions/domain вынесены в отдельные owning modules.

API imports могут идти через публичный façade. Внутренние cross-domain зависимости привязываются к owning module, если тест или caller должен подменять именно execution dependency. Это предотвращает ложные monkeypatch boundaries после декомпозиции.

## 2. Runtime services

Production-shaped `compose.yaml` определяет:

- `postgres` — PostgreSQL;
- `migrate` — one-shot `alembic upgrade head`;
- `db-permissions` — one-shot установка runtime grants;
- `backend` — FastAPI/uvicorn;
- `telegram-worker` — Telegram outbox consumer;
- `email-worker` — optional profile, email outbox consumer;
- `maintenance-worker` — technical retention;
- `web` — Nginx + собранный frontend.

Миграции выполняются DB owner identity. Runtime processes не должны использовать owner connection string.

## 3. Сети и egress

Логическое разделение:

| Сеть | Кто подключён | Назначение |
|---|---|---|
| `app_net` | web, backend | HTTP между reverse proxy и API |
| `db_net` | postgres, backend, delivery/maintenance workers, one-shot DB jobs | доступ к PostgreSQL |
| `ingress_net` | web в base compose | локальный TCP ingress; production override удаляет сеть |
| `egress_net` | Telegram/email workers | внешний HTTPS egress |

`app_net` и `db_net` internal. Backend не подключён к egress network. Telegram/email secrets не передаются backend, если они не нужны его роли.

Production `compose.ingress-unix.yaml` удаляет host TCP publication web-контейнера и ingress network, монтируя контролируемый каталог Unix socket.

## 4. HTTP path пользователя

1. TLS завершается на host Nginx.
2. Host Nginx принимает только ожидаемый hostname и проксирует в Unix socket.
3. Web Nginx:
   - отдаёт статические React assets;
   - проксирует `/api/*` в backend;
   - перезаписывает forwarded/IP headers;
   - применяет rate limits;
   - добавляет security headers.
4. FastAPI:
   - применяет TrustedHost в production;
   - добавляет `Cache-Control: no-store` к API;
   - проверяет session/access/capability;
   - выполняет domain transaction в PostgreSQL.
5. JSON response возвращается тем же путём.

Browser никогда не обращается к PostgreSQL напрямую.

## 5. Authentication path

```text
frontend
  │ GET /api/auth/me
  ├── valid cookie session ─────────────► AuthState
  │
  └── 401
      │
      ├── load vendored Telegram SDK
      ├── read initData
      └── POST /api/auth/telegram
             │
             ├── verify HMAC/freshness
             ├── reconcile TelegramIdentity/User
             ├── create server session
             └── HttpOnly cookie + AuthState
```

Cookie-authenticated state-changing requests дополнительно проверяются по `Origin` против configured Mini App origin.

Access status и role — разные оси. Подробнее: [ACCESS_AND_RBAC.md](ACCESS_AND_RBAC.md).

## 6. Transaction ownership

`DbSession` создаёт request-scoped `AsyncSession`, но не делает commit автоматически. Commit/rollback принадлежит API/use-case boundary.

Это принципиально для cross-domain операций:

- Procurement acceptance вызывает Warehouse service и завершает закупку в одной транзакции;
- access decision обновляет User/AccessRequest и enqueue notification в одной транзакции;
- Catalog item create/update меняет Item и EAV как единое изменение.

Service-функции не должны скрыто commit-ить внутри себя.

## 7. PostgreSQL как вторая граница корректности

Критичные правила не оставлены только на Python-уровне. Readiness проверяет:

- единственный ожидаемый Alembic head;
- наличие/включённость критичных triggers;
- функции Catalog identity и Warehouse projection;
- требуемую collation;
- наличие колонок критических таблиц.

DB triggers защищают:

- category/leaf consistency;
- typed/required EAV;
- derived catalog identity;
- warehouse append-only history и movement shape;
- custody holder eligibility;
- procurement immutable revisions/events/bindings;
- current revision/final movement integrity;
- role/access audit coupling.

## 8. Catalog path

```text
Category configuration/migrations
        │
        ▼
Category + CategoryAttribute
        │
create/update Item
        ▼
validation → normalization → identity_signature
        │
        ├── Item
        └── typed ItemAttributeValue
```

Catalog identity — technical identity номенклатуры. Она используется Procurement для проверки, что согласованная proposed line связывается именно с эквивалентным Item.

Подробнее: [CATALOG.md](CATALOG.md).

## 9. Warehouse path

```text
API mutation
  │
  ├── capability + mutation safety gate
  ├── idempotency key/fingerprint
  ├── deterministic locks
  ├── validate stock/custody/location/item
  ├── INSERT Movement + MovementLine
  └── refresh_warehouse_projection(...)
           │
           ├── StockBalance
           └── UserItemCustodyBalance
```

History — source of truth; projections пересчитываются в той же транзакции. Подробнее: [WAREHOUSE.md](WAREHOUSE.md).

## 10. Procurement path

```text
create request
  │
  ▼
immutable revision #1
  │
manager actions / corrections / new immutable revisions
  │
  ▼
AWAITING_ACCEPTANCE
  │
  ├── bind proposed lines to matching Catalog Item
  └── report discrepancy
  │
technical acceptance
  │ same DB transaction
  ├── create Warehouse RECEIPT
  ├── bind final_movement_id
  ├── set COMPLETED
  └── append ProcurementEvent + notifications
```

Подробнее: [PROCUREMENT.md](PROCUREMENT.md).

## 11. Notification path

Система использует **transactional outbox**. Backend не вызывает Telegram/Graph внутри основной предметной транзакции.

```text
domain transaction
    │
    └── INSERT outbox intent + COMMIT
                         │
                         ▼
worker claim with SKIP LOCKED
                         │
                  external provider
                         │
                 finalize claim token
```

Dedupe ограничивает повторное создание intent. Потерянный внешний response может привести к повторной доставке, поэтому guarantee — at-least-once.

Подробнее: [NOTIFICATIONS.md](NOTIFICATIONS.md).

## 12. Frontend path

Startup:

1. начинается lazy preload requested route;
2. `TelegramAccessGate` сначала пробует существующую cookie session;
3. при 401 загружается локальная vendored копия Telegram Web App SDK;
4. после APPROVED рендерится router;
5. page data загружается React Query.

Frontend содержит UX capability guards, но API остаётся security boundary.

Подробнее: [FRONTEND.md](FRONTEND.md).

## 13. Release и provenance

Каждый production image имеет:

- reference с full Git SHA;
- immutable Docker image ID;
- OCI label `org.opencontainers.image.revision`.

Release manifest связывает source SHA и image IDs. Runtime provenance собирает фактически запущенные image IDs/revision labels и сравнивает их с approved release.

## 14. Backup и recovery boundary

Backup фиксирует:

- clean production checkout SHA;
- runtime image provenance;
- Alembic head;
- PostgreSQL tool version;
- dump object key, size и SHA-256;
- S3 VersionId dump и manifest.

Recovery rehearsal использует конкретные versioned objects и точные runtime artifacts из manifest в изолированных Docker network/volume/container. Production cutover — отдельная операция.

## 15. Failure model

Система fail-closed в основных границах:

- несоответствие schema head/critical triggers → readiness 503;
- отсутствующие production auth secrets → backend startup error;
- отсутствующий Telegram Gateway/email config → соответствующий worker не стартует;
- mutation gate false → catalog/inventory mutations 423;
- DB conflict/serialization/deadlock → контролируемый conflict/retryable response;
- stale outbox claim → finalization игнорируется;
- unknown public host → host ingress не обслуживает приложение.
