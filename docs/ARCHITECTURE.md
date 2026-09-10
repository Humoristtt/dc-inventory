# Architecture

## System

Spikatel Inventory — Telegram Mini App.

Основной путь:

Telegram → HTTPS / Cloudflare → nginx → FastAPI → PostgreSQL

Backend modules:

- auth / identity;
- access;
- catalog;
- inventory;
- notifications;
- telegram_bot;
- maintenance.

## Catalog

Каталог использует фиксированную hierarchy family → leaf.

Item является номенклатурной позицией.
Технические поля зависят от leaf category.
Search/facets выполняются backend и scoped текущим universe.

CatalogQuerySpec carries request-scoped category IDs and attribute definitions.
Preparation reads category metadata once; facets reuse it without global caching.
Availability filters/facets use indexed stock existence checks (nonnegative
quantities), while item list quantities retain the stock aggregate.

## Frontend startup

React renders the access shell immediately. SDK loading runs independently of
cookie-session lookup; Telegram authentication waits for SDK completion after
an unauthenticated response. The auth exchange stays shared across StrictMode
remounts. BackButton/fullscreen controls subscribe to delayed SDK availability.

The module for the current pathname starts loading in parallel with startup
authentication. After the approved application mounts, the small fixed route
set is warmed in the background. Routes remain dynamic imports and outside the
initial JS import graph; the production bundle contract continues to enforce
that boundary.

`RouteContent` provides the accessible Suspense/error recovery boundary without
being remounted solely because the pathname changed. Navigation changes reset a
failed route boundary.

Catalog navigation uses cached family/leaf hierarchy metadata to start
independent leaf-item loading without waiting for category-detail completion.
A visible family page prefetches only its child leaf metadata. Item navigation
can paint from the catalog-list payload as React Query placeholder data while
the canonical item endpoint revalidates in the background.

Authenticated query data remains in-memory only; persistent browser query
storage is not part of the MVP.

Detailed rationale and acceptance are canonical in
`docs/FRONTEND_PERFORMANCE.md`.

## Warehouse

Источник истины — immutable movement journal.

Current projection:

stock_balances(Item, Location, quantity)

user_item_custody_balances(User, Item, quantity)

`actor_user_id` фиксирует исполнителя операции, а `custody_user_id` — пользователя,
физически ответственного за оборудование. USER ISSUE/RETURN изменяют custody;
ADMIN ISSUE/RETURN остаются административными движениями склада без custody.

Movement types:

- RECEIPT;
- ISSUE;
- RETURN;
- TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

MovementLine хранит Item snapshot и positive quantity.

## Transaction model

Создание movement выполняется одной PostgreSQL transaction:

1. normalize client_request_id;
2. advisory-lock idempotency key;
3. проверить replay/fingerprint;
4. lock original movement при необходимости;
5. lock locations;
6. lock Items;
7. batch-lock StockBalance ordered by (item_id, location_id);
8. batch-lock UserItemCustodyBalance ordered by item_id;
9. insert Movement header and apply stock/custody deltas;
10. insert immutable MovementLine rows and enqueue transactional outbox effects;
11. commit.

Negative stock/custody запрещён. Zero balance rows удаляются. REVERSAL наследует
custody исходного movement; CORRECTION custody-bearing movement запрещён fail-closed.

## Idempotency

Scope:

actor_user_id + client_request_id

Fingerprint включает custody context. Replay одинакового payload возвращает
существующий Movement.
Другой payload под тем же ключом возвращает conflict.

## Notifications

Telegram delivery использует PostgreSQL transactional outbox.

ISSUE notification создаётся до commit warehouse transaction.

Outbox имеет deterministic dedupe key.
Delivery worker выполняет retry/DEAD lifecycle независимо от warehouse request.

TELEGRAM_DELIVERY_GUARANTEE=AT_LEAST_ONCE_NOT_EXACTLY_ONCE

### Duplicate delivery window

Transactional outbox гарантирует сохранность notification intent, но внешний
Telegram Bot API не предоставляет системе атомарный commit вместе с локальным
delivery-state update. Если Telegram принял сообщение, а worker завершился до
фиксации успешной доставки в PostgreSQL, notification может быть отправлена повторно
после retry.

Поэтому delivery semantics — at-least-once, а не exactly-once. Dedupe key
защищает от повторного создания одного и того же outbox intent внутри системы,
но не превращает внешний Bot API delivery в exactly-once transport.

## Runtime provenance

Application image фиксирует source revision в OCI metadata:

`org.opencontainers.image.revision`

Git checkout на production VM и revision реально запущенного container image
являются разными operational facts. Runtime provenance проверяется по metadata
образа, а не выводится только из состояния checkout.

## Authorization

Approved USER:

- catalog;
- stock;
- own actor movement history;
- ISSUE;
- RETURN.

ADMIN дополнительно:

- общий journal;
- employee filter;
- Item/Location administration;
- RECEIPT;
- TRANSFER;
- WRITE_OFF;
- CORRECTION/REVERSAL.

Frontend authorization не является security boundary.

## Safety gate

Regular warehouse mutation API защищён:

`REAL_INVENTORY_MUTATIONS_ENABLED`

Production default остаётся `false`.

Initial production inventory bootstrap использует отдельный one-shot CLI
boundary и намеренно требует, чтобы regular mutation gate оставался закрытым.

Таким образом initial load не является обходом или включением normal mutation
API.

## Reconciliation

Projection consistency проверяется:

backend/scripts/reconcile_inventory_projections.sql

Zero returned rows означает, что stock и custody projections совпадают с journal.

## Bootstrap

Authoritative initial workbook находится вне repository.

Bootstrap architecture состоит из двух boundaries:

1. `app.bootstrap.inventory_workbook`
   - читает и валидирует workbook;
   - нормализует Item identity;
   - агрегирует deterministic duplicates;
   - создаёт opening RECEIPT через warehouse service;
   - защищается от populated catalog/journal.

2. `app.bootstrap.production_inventory`
   - production-only guarded one-shot entry point;
   - требует production Docker PostgreSQL boundary;
   - требует закрытый regular mutation gate;
   - проверяет source SHA/count contract;
   - проверяет empty warehouse domain;
   - создаёт location + inventory атомарно;
   - проверяет resulting counts/quantities;
   - выполняет canonical projection reconciliation до commit;
   - fail-closed откатывает transaction при любой ошибке.

Initial production bootstrap принят 2026-09-08.

Повторный initial bootstrap в текущую production DB запрещён.
