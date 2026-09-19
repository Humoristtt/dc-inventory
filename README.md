# Инвентаризация оборудования ЦОД — Spikatel Inventory

Telegram Mini App для количественного учёта оборудования и расходных материалов ЦОД. PostgreSQL — источник истины: остатки изменяются только складскими операциями, immutable movement journal сохраняет историю. Код организован как модульный монолит с отдельными модулями auth/access, catalog, inventory, procurement и notifications.

## Актуальность данных — 19.09.2026

Нельзя смешивать подтверждённое production-состояние, состояние исходного кода и локальные результаты тестов.

| Контур | Последняя подтверждённая информация |
|---|---|
| Production | Checkout/runtime `6d9bafef494f910b9bd1ebea7c5b7cf45f853742`, схема `c3d4e5f6a7b8`; Procurement и пяти-ролевая RBAC развёрнуты. Это **последняя документированная проверка**, не live monitoring. |
| Source `remediation/audit-0-12` | Alembic head `a9c0d1e2f3a4`; CP-07–12 зафиксированы в исходниках, но production acceptance не выполнена. |
| Операционные ограничения | `REAL_INVENTORY_MUTATIONS_ENABLED=false`; первоначальный импорт выполнен через отдельный one-shot bootstrap. |

    ALEMBIC_HEAD=c3d4e5f6a7b8
    SOURCE_ALEMBIC_HEAD=a9c0d1e2f3a4

Исторические результаты — `docs/HISTORY.md`; текущее состояние production нужно заново сверить перед deploy. Git push/source-only sync не обновляет схему или уже запущенные контейнеры.

Текущая post-cutover source-фаза:

    CP-13: аудит документации
      -> CP-14: изолированная full-stack приёмка
      -> CP-15: трёхпроходный pre-deployment аудит
      -> CP-16: согласованное production deployment
      -> CP-17: реальная приёмка Telegram Mini App
      -> CP-18: независимый повторный аудит

CP-07 требует согласованного переключения Tunnel/web с TCP на trusted Unix ingress, проверки UID/GID и rollback; новый web image нельзя выпускать при старом Tunnel origin. CP-08/09/10/11 имеют отдельные незавершённые production gates: live delivery, permission cutover, runtime provenance, настоящий S3 restore rehearsal. Локальный PASS не равен production PASS. Статусы и evidence: `docs/AUDIT_0_12_REMEDIATION.md`, процедура CP-07: `docs/CP07_HTTP_SOCKET_MIGRATION.md`.

## Warehouse Domain V2

Warehouse Domain V2 развёрнут и принят в production. `Item` — номенклатура, а не physical unit. `StockBalance` = Item × StorageLocation × positive quantity, `UserItemCustodyBalance` = User × Item × positive quantity. Actor (`actor_user_id`) и custody (`custody_user_id`) различаются. ENGINEER/SENIOR_ENGINEER ISSUE/RETURN меняют custody; ADMIN/OWNER административные movements не создают её автоматически. Отрицательные остатки запрещены, нулевые строки удаляются.

Immutable journal поддерживает RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION и REVERSAL. Финальный procurement RECEIPT нельзя подвергать generic CORRECTION/REVERSAL: для отмены completed procurement нужен отдельный business workflow. Движения, projections и outbox фиксируются одной транзакцией. Нет active serial/WWN/physical-unit lifecycle и отдельного пользовательского экрана «Моё оборудование»; custody существует как backend integrity projection.

Первоначальное production-наполнение склада также завершено:

- внешний authoritative operator workbook хранится вне Git и прошёл fail-closed validation;
- guarded one-shot CLI создал одну opening RECEIPT transaction;
- проверены counts/quantities, post-import reconciliation zero drift, health, fresh verified off-VM backup и real Telegram visual acceptance.

Повторный initial bootstrap запрещён. Обычные складские mutations остаются заблокированы отдельной границей `REAL_INVENTORY_MUTATIONS_ENABLED=false` до явного go-live решения.

## Каталог, роли, закупки

Versioned fixed family → leaf hierarchy включает трансиверы Ethernet/FC, оптику, сетевые адаптеры Ethernet/FC, SSD/HDD, RAM, PCIe-адаптеры и питание. Item создаётся только в leaf, «Дальние» — derived scope, а не category. Технические поля/identity зависят от leaf schema (`docs/CATALOG_SCHEMA.md`).

production и source используют capability-based five-role RBAC: `ENGINEER`, `SENIOR_ENGINEER`, `MANAGER`, `ADMIN`, `OWNER`. Роль и access status хранятся в PostgreSQL; backend выводит capabilities и проверяет каждый protected action. MANAGER — отдельная ветка закупок, assigned Manager означает ответственность, не ACL. OWNER singleton/recovery и не назначается обычным API. Procurement immutable revisions/events; manager status не изменяет stock. Техническая финальная приёмка атомарно создаёт ровно один Warehouse RECEIPT. Полный контракт: `docs/RBAC_PROCUREMENT.md`.

## Telegram, email, безопасность

Telegram `initData` проверяется backend; пользовательская сессия хранится server-side и выдаётся через HttpOnly cookie. Webhook дедуплицирует update ID; доставка идёт через PostgreSQL outbox, отдельный Telegram worker и Cloudflare Worker Gateway. Production VM не выполняет прямые Bot API вызовы к `api.telegram.org:443`.

Внешняя Telegram/email доставка — **at-least-once**, не exactly-once: dedupe key предотвращает повторное создание outbox intent, но при lost acknowledgement отправка может повториться. Microsoft Graph email worker source реализован и изолирован отдельной PostgreSQL identity, однако production по умолчанию выключен `EMAIL_DELIVERY_ENABLED=false`: secrets, profile `email` и live acceptance отдельно.

Реальные inventory datasets, workbook contents, credentials, database dumps, private/runtime-only production identifiers и operator source artifacts запрещены в публичном репозитории. Публичные service identifiers (host Mini App, support username) могут находиться в документации и исходниках по назначению.

## Технологии и эксплуатация

Python 3.12, FastAPI, SQLAlchemy 2 async, asyncpg, Alembic; PostgreSQL 18; React/TypeScript/Vite, Vitest/Playwright; Nginx, Docker Compose, Cloudflare Tunnel/Worker. Production VM — Ubuntu 24.04 LTS. Backend/PostgreSQL не публикуют host ports, текущий web bind — `127.0.0.1:8080` до CP-07 migration. Отдельные database identities: owner/migrator, backend, Telegram, optional email и maintenance.

OCI image label `org.opencontainers.image.revision` фиксирует source revision самого образа; Git checkout и running image — разные факты. Source-only docs/host-tools sync без rebuild допустим только при неизменных application runtime source/Docker build contexts. `ops/release/build_release.py` публикует manifest/env после проверки всех release artifacts.

## Документы

- `docs/ROADMAP.md` — последовательность этапов; `docs/AUDIT_0_12_REMEDIATION.md` — CP-00–18 и открытые acceptance; `docs/HISTORY.md` — исторические доказательства.
- `docs/ARCHITECTURE.md`, `docs/WAREHOUSE_DOMAIN.md`, `docs/CATALOG_SCHEMA.md`, `docs/RBAC_PROCUREMENT.md` — архитектура и предметные контракты.
- `docs/DEVELOPMENT.md`, `docs/FRONTEND_DESIGN_SYSTEM.md`, `docs/FRONTEND_PERFORMANCE.md` — локальная разработка и UI.
- `docs/DEPLOYMENT.md`, `docs/OPERATIONS.md`, `docs/RECOVERY_RUNBOOK.md`, `docs/CP07_HTTP_SOCKET_MIGRATION.md` — выпуск, эксплуатация и восстановление.
- Документы Stage 15/source reference исторические; их старые snapshots не следует превращать в нынешний production state.
