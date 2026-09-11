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

Frontend catalog URL state uses category-aware implicit sort defaults.
Transceiver scopes (`transceivers`, `transceiver_ethernet`,
`transceiver_fc`) default to `available desc`; ordinary categories default to
`name asc`. URL parsing and serialization receive the same contextual default:
absence of `sort`/`order` means that default, while an explicit non-default
selection remains round-trip stable. Quick-sort controls modify this same
server-side catalog query state; no separate client-side sorting model exists.

Compound `reach` formatting is presentation-only: card/detail rendering may
replace human-readable `/` or `;` separators with middle dots, while the stored
attribute value and backend catalog contract remain unchanged.

## Frontend design system

Нормативный визуальный контракт и ownership rules находятся в `docs/FRONTEND_DESIGN_SYSTEM.md`. Этот файл является источником истины для shared headers, buttons, form controls, typography и responsive UI primitives. Feature CSS не является design-system boundary.

Frontend typography and form geometry use shared CSS design tokens rather than
page-local arbitrary sizes.

The typography scale defines common roles for kicker/meta/secondary/body/control/
emphasis/card-title/section-title/page-title text. Equipment cards, item detail
and catalog forms consume these roles so readability changes can be tuned from
one contract instead of diverging per page.

Single-line form controls share one responsive geometry contract:

- mobile/default: `52px`;
- tablet (`>=680px`): `56px`;
- desktop (`>=1100px`): `60px`.

Input, select, combobox and equivalent single-line controls are expected to use
the same height, font size, horizontal padding and radius at a given breakpoint.
Textarea uses a separate shared minimum-height token.

The current product workflow is desktop-first for visual acceptance: desktop is
tuned first while the responsive tablet/mobile contract remains functional.
Tablet/mobile visual polish is intentionally deferred until the desktop feature
set is complete; responsive behavior is not removed or replaced by a fixed
desktop-only layout.

Desktop content remains centered and width-bounded rather than stretching
indefinitely on ultrawide displays. Browser acceptance covers compact desktop,
`1920x1080` and ultrawide desktop viewports. Vertical content continues to use
normal document scrolling / viewport-bounded dialogs instead of scaling UI to
fill screen height.

Catalog detail and equipment create/edit pages share the same branded
toolbar/kicker/page-title header hierarchy. Section titles are intentionally
smaller than page titles, while field labels and values remain readable enough
to avoid the previous oversized-heading/small-data contrast.

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

## Authorization / RBAC target

Current feature-cycle contract:

`docs/RBAC_PROCUREMENT.md`

Target roles:

- ENGINEER;
- SENIOR_ENGINEER;
- MANAGER;
- ADMIN;
- OWNER.

Role хранится на User.

Capabilities вычисляются backend policy и являются authorization boundary.
Frontend visibility не заменяет backend authorization.

Role hierarchy не моделируется простым числовым `role >= ...`, потому что
MANAGER является отдельной бизнес-веткой, а не уровнем складской иерархии.

OWNER является singleton recovery role, привязанной к configured recovery
Telegram identity.

ADMIN может назначать ENGINEER / SENIOR_ENGINEER / MANAGER, но не ADMIN/OWNER.
OWNER может назначать ADMIN. OWNER нельзя изменять обычным role/access API.

До завершения migration фактический production baseline всё ещё использует
исторические USER/ADMIN значения.

## Procurement architecture target

Procurement реализуется отдельным modular-monolith module и не встраивается в
catalog/inventory models.

Главный invariant:

procurement status не является warehouse stock mutation.

Procurement использует immutable revisions и immutable event trail.

Assigned Manager является business responsibility, а не authorization ACL.
Любой MANAGER может выполнять допустимые actions, при этом event хранит
фактического actor.

Final acceptance выполняется атомарно:

Procurement row lock
-> validate active revision
-> validate catalog bindings/location
-> create immutable Warehouse RECEIPT
-> link movement
-> complete procurement
-> enqueue notifications
-> commit.

Discrepancy path не создаёт movement и не меняет stock.

Первый procurement implementation не поддерживает partial acceptance.

Подробный state machine, role matrix и acceptance criteria находятся в
`docs/RBAC_PROCUREMENT.md`.

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
