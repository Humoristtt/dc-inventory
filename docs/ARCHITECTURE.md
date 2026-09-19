# Архитектура Spikatel Inventory

Telegram Mini App: Telegram/браузер → Cloudflare HTTPS/Tunnel → Nginx → FastAPI → PostgreSQL. Модульный монолит: `auth/identity`, `access`, `catalog`, `inventory`, `procurement`, `notifications`, `telegram_bot`, `maintenance`. PostgreSQL — каноническое хранилище; frontend не является авторизационной границей. Текущая source схема — Alembic `a9c0d1e2f3a4`; последний документированный production schema head — `c3d4e5f6a7b8`, различие требует отдельной миграции и acceptance.

## Каталог

Fixed versioned family → leaf hierarchy. `Item` — номенклатура, leaf schema задаёт required/optional технические attributes и deterministic identity. Search/facets вычисляются backend внутри request-scoped universe. `CatalogQuerySpec` хранит category IDs/attribute definitions; category metadata читается один раз на подготовку запроса, без глобального cache. Stock availability использует indexed existence checks, карточки — stock aggregation.

Контекстный URL sort: transceiver scopes по умолчанию `available desc`, другие категории `name asc`; parser/serializer используют общий default, explicit non-default round-trip сохраняется. Quick-sort изменяет тот же server-side query, не отдельную client-side сортировку. Reach display может заменять разделители точками без изменения сохранённого attribute value.

## Frontend

React + TypeScript + Vite. `docs/FRONTEND_DESIGN_SYSTEM.md` определяет единые header/button/form/typography/responsive tokens и ownership `shared/ui`; feature CSS задаёт только предметный layout. Основные control heights: mobile 52px, tablet ≥680px 56px, desktop ≥1100px 60px; textarea имеет отдельный min-height. Общий toolbar/title/kicker contract используется на Catalog/Item/Location/Movement/Admin pages; desktop content ограничен по ширине, dialogs — по viewport.

React access shell отрисовывается немедленно. Telegram SDK загрузка параллельна проверке cookie-session, unauthenticated auth exchange ждёт SDK, используется shared flow через StrictMode remounts. Текущий route chunk начинает загружаться параллельно auth, фиксированный набор route chunks прогревается после APPROVED, оставаясь dynamic imports вне initial bundle. `RouteContent` сохраняет Suspense/error recovery boundary между pathname changes. Catalog hierarchy cache позволяет загружать leaf items параллельно category details; Item detail показывает placeholder из списка и затем revalidates canonical endpoint. Authenticated query cache — только in-memory. Подробнее: `docs/FRONTEND_PERFORMANCE.md`.

## Warehouse Domain V2

Источник истории — immutable Movement/MovementLine journal. Текущие projections:

    stock_balances(Item, Location, quantity)
    user_item_custody_balances(User, Item, quantity)

`actor_user_id` — исполнитель движения; `custody_user_id` — сотрудник, за которым числится quantity. ENGINEER/SENIOR_ENGINEER ISSUE/RETURN меняют custody; ADMIN/OWNER — administrative movements без personal custody. Отрицательные остатки запрещены, zero rows удаляются. Поддерживаются RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION, REVERSAL; финальный Procurement RECEIPT не допускает generic CORRECTION/REVERSAL.

Warehouse transaction: нормализовать `client_request_id` → advisory-lock idempotency → replay/fingerprint check → lock original movement при необходимости → lock user/location/Items → batch lock stock/custody balances ordered → вставить Movement и lines, изменить projections, enqueue outbox → commit. Fingerprint включает custody; identical replay возвращает движение, changed payload — conflict. Движение и outbox intent коммитятся вместе. Journal feed использует server snapshot/MVCC и HMAC-signed opaque cursor; неподписанные snapshot parameters не являются публичным API. Schema/domain details — `docs/WAREHOUSE_DOMAIN.md`.

## Notification delivery

ISSUE и procurement notifications используют durable PostgreSQL outbox с deterministic dedupe key; worker выполняет lease/claim/retry/DEAD. Telegram `/start` welcome сверяет актуальный claim token перед изменением chat state и фиксирует outbox/chat state в одной DB transaction. Внешний Telegram Bot API и Microsoft Graph не могут коммитить side effects атомарно вместе с PostgreSQL: доставка at-least-once, duplicate external delivery при lost acknowledgement возможна. Exactly-once не заявляется. Email worker optional, `EMAIL_DELIVERY_ENABLED=false` по умолчанию, отдельная DB identity и explicit profile `email`.

## Runtime provenance и ingress

Docker images содержат source revision в OCI metadata `org.opencontainers.image.revision`. Runtime provenance сверяет заявленный checkout с фактическим Git HEAD и получает immutable image IDs/labels; checkout и running image revision — разные operational facts, в частности после допустимого source-only sync. `ops/release/build_release.py` публикует release artifacts только после успешной проверки всех images.

CP-07 локально реализовал два входа Nginx: недоверенный TCP `:8080` и trusted Unix `/run/dc-inventory/ingress.sock` (`set_real_ip_from unix:`, `real_ip_header CF-Connecting-IP`). Защита socket основана на parent-directory permissions. Production Tunnel по последней зафиксированной проверке остаётся на `http://localhost:8080`; нельзя разворачивать новый web образ без одновременной смены Tunnel ingress и проверки UID/GID. Порядок и rollback — `docs/CP07_HTTP_SOCKET_MIGRATION.md`.

## Authorization / RBAC

Source roles:

- ENGINEER;
- SENIOR_ENGINEER;
- MANAGER;
- ADMIN;
- OWNER.

Роль хранится на User; capabilities вычисляются backend. MANAGER — отдельная бизнес-ветка, не числовой уровень. OWNER singleton/recovery и не назначается обычным API. ADMIN назначает только стандартные роли, OWNER может назначать ADMIN. RBAC migration `a1b2c3d4e5f6` уже принята в production; canonical contract: `docs/RBAC_PROCUREMENT.md`.

## Procurement

Отдельный bounded module. Статус закупки не меняет stock. Immutable revisions/events; assigned Manager — ответственность, не ACL. Final acceptance: lock request → verify status/current revision/bindings/location → создать immutable Warehouse RECEIPT → link final movement → завершить закупку → enqueue notifications → commit. Discrepancy не создаёт movement. Partial acceptance в первой версии отсутствует. Source head `a9c0d1e2f3a4` включает защиту канонической expected item identity и DB invariants; production acceptance новых source изменений остаётся OPEN.

## Safety, reconciliation и bootstrap

Regular mutation boundary: `REAL_INVENTORY_MUTATIONS_ENABLED`. Production default остаётся `false`. Initial inventory не включал normal mutations: отдельный guarded one-shot `app.bootstrap.production_inventory` требует production Docker PostgreSQL, closed gate, external workbook SHA/counts, empty warehouse, APPROVED ADMIN, атомарное создание location + RECEIPT, post-write checks и zero-drift reconciliation до commit. Повторный bootstrap запрещён.

`app.bootstrap.inventory_workbook` выполняет workbook validation/normalization, `app.bootstrap.production_inventory` — production-only safety boundary. Workbook и реальные values вне Git. Read-only `backend/scripts/reconcile_inventory_projections.sql` пересчитывает stock и custody по journal; zero rows — PASS, drift — blocker, автоматический repair не выполняется. Recovery использует schema-version-matched reconciliation SQL из exact backend image, зафиксированного в backup manifest. Состояние CP-00–18 — `docs/AUDIT_0_12_REMEDIATION.md`.
