# План разработки Spikatel Inventory

Канонический roadmap после перехода на Warehouse Domain V2.

Статусы:

- [x] завершено;
- [~] текущая приёмка;
- [ ] будущая работа.

Последнее обновление: 2026-09-12.

## 1. Базовая платформа

- [x] Telegram Mini App.
- [x] FastAPI backend.
- [x] PostgreSQL.
- [x] Docker Compose production-shaped runtime.
- [x] Cloudflare / HTTPS production path.
- [x] Telegram initData server-side validation.
- [x] HttpOnly server session.
- [x] Historical ADMIN / USER access model на accepted production baseline; source RBAC уже five-role capability-based.
- [x] Access request approve/reject через Telegram.
- [x] Transactional notification outbox.
- [x] Fail-closed mutation gate.

## 2. Warehouse Domain V2

- [x] Quantity-only inventory.
- [x] Удалена active physical-unit model.
- [x] Удалена legacy physical-unit holder model.
- [x] Actor операции отделён от custody пользователя.
- [x] UserItemCustodyBalance = User × Item × positive quantity.
- [x] ENGINEER / SENIOR_ENGINEER RETURN ограничен фактическим custody balance.
- [x] StockBalance = Item × Location × quantity.
- [x] Zero balances не хранятся.
- [x] Negative stock запрещён.
- [x] Location first-class entity.
- [x] WAREHOUSE / DATACENTER location types.
- [x] Location archive запрещён при наличии stock.
- [x] Immutable movement journal.
- [x] RECEIPT.
- [x] ISSUE.
- [x] RETURN.
- [x] TRANSFER.
- [x] WRITE_OFF.
- [x] CORRECTION.
- [x] REVERSAL.
- [x] Idempotent mutation API.
- [x] PostgreSQL concurrency locking.
- [x] Read-only projection reconciliation.

## 3. Permissions

ENGINEER:

- [x] Browse/search/filter catalog.
- [x] Read stock / locations.
- [x] Read own actor history.
- [x] ISSUE / RETURN / RECEIPT / TRANSFER.

SENIOR_ENGINEER:

- [x] ENGINEER warehouse operations.
- [x] Common movement journal / employee filter.
- [x] Catalog create/edit/archive.

MANAGER:

- [x] Catalog / stock / locations read-only.
- [x] Warehouse mutations denied.
- [x] Movement journal denied.

ADMIN / OWNER:

- [x] Common movement journal / employee filter.
- [x] Location administration.
- [x] Catalog administration.
- [x] RECEIPT / ISSUE / RETURN / TRANSFER.
- [x] WRITE_OFF / CORRECTION / REVERSAL.

## 4. Catalog V2

- [x] Fixed family → leaf hierarchy.
- [x] Трансиверы / Ethernet.
- [x] Трансиверы / Fibre Channel.
- [x] Оптика / Оптические патч-корды.
- [x] Оптика / Сплиттеры и делители.
- [x] Сетевые адаптеры / Ethernet.
- [x] Сетевые адаптеры / Fibre Channel.
- [x] Накопители / SSD.
- [x] Накопители / HDD.
- [x] Оперативная память.
- [x] PCIe-адаптеры.
- [x] Кабели питания.
- [x] Только leaf category содержит Items.
- [x] Дальние — derived scope, не category.
- [x] Reach normalization.
- [x] Dynamic scoped facets.
- [x] Single-value facet dimension скрывается.
- [x] Optional patch-cord color.
- [x] Admin item create/edit/archive UX.

## 5. Warehouse UI

- [x] Family/leaf navigation.
- [x] Search.
- [x] Dynamic filters.
- [x] Item detail.
- [x] Total stock.
- [x] Stock breakdown по location.
- [x] ENGINEER / SENIOR_ENGINEER Взять / Вернуть.
- [x] ENGINEER / SENIOR_ENGINEER Переместить / Приход.
- [x] ADMIN / OWNER Списать.
- [x] Movement journal capability-aware.
- [x] Employee filter только для movement.read_all.
- [x] Category/location/type filters.
- [x] Period presets 7d / 30d / 3m / year / all.
- [x] 3 месяца default.

## 6. Archived lifecycle

- [x] Archived Item запрещает RECEIPT.
- [x] Archived Item запрещает ISSUE.
- [x] Archived Item допускает RETURN.
- [x] Archived Item допускает TRANSFER.
- [x] Archived Item допускает WRITE_OFF.
- [x] Archived Item допускает CORRECTION.
- [x] Archived Item допускает REVERSAL.

## 7. Initial inventory bootstrap

- [x] Workbook parser.
- [x] Quantity normalization.
- [x] Duplicate identity aggregation.
- [x] Patch-cord optional color mapping.
- [x] Explicit SSD/HDD classification.
- [x] Dry-run.
- [x] Opening RECEIPT.
- [x] Double-import protection.
- [x] Authoritative workbook хранится вне repository.

## 8. Telegram inventory notifications

- [x] Configured notification recipient получает notification на ISSUE.
- [x] Notification создаётся transactional с movement.
- [x] Idempotent replay не создаёт duplicate notification.
- [x] RETURN не создаёт ISSUE notification.

## 9. Production acceptance Warehouse V2

- [x] Backend PostgreSQL tests.
- [x] Ruff.
- [x] mypy.
- [x] Frontend typecheck.
- [x] Frontend lint.
- [x] Frontend unit tests.
- [x] Frontend build.
- [x] Warehouse synthetic browser E2E.
- [x] Frontend → API → PostgreSQL fullstack CI acceptance.
- [x] Projection reconciliation zero drift.
- [x] Warehouse Domain V2 merge/deploy.
- [x] Responsive/mobile/desktop warehouse UI acceptance.
- [x] Header/fullscreen/Escape remediation.
- [x] Desktop form consistency and smart suggestions.
- [x] Accepted production migration head `f8a9b0c1d2e3`.
- [x] External authoritative workbook contract.
- [x] Fail-closed production one-shot bootstrap path.
- [x] Empty-domain production preflight.
- [x] Fresh verified pre-import off-VM backup.
- [x] Initial production inventory bootstrap.
- [x] Post-import DB/count/quantity verification.
- [x] Post-import projection reconciliation zero drift.
- [x] Fresh verified post-import off-VM backup.
- [x] Real Telegram visual acceptance.

## 10. Accepted clean baseline

Предыдущий Warehouse/UX/design-system cycle завершён.

Accepted production/runtime golden baseline перед новым feature cycle:

`1242f56c131d0f8c470e05cbaf209c48a37e85a4`

Подтверждено:

- [x] Warehouse Domain V2 production acceptance;
- [x] frontend performance pass;
- [x] typography/form consistency;
- [x] shared frontend design-system refactor;
- [x] catalog speed sorting / strict long-range scope;
- [x] post-PR60 Telegram UX remediation;
- [x] required CI;
- [x] production cutover;
- [x] real Telegram desktop acceptance;
- [x] fresh verified production backup;
- [x] production Docker/release cleanup;
- [x] Mac project Docker cleanup;
- [x] GitHub cleanup до единственной `main`;
- [x] local/source/runtime golden-state verification.

Новый feature branch начинается от этого exact baseline.

Документационные и feature commits после baseline не являются production state
до отдельного merge/deploy/provenance acceptance.

Regular warehouse mutation gate на accepted production baseline:

`REAL_INVENTORY_MUTATIONS_ENABLED=false`

Initial bootstrap завершён и повторно не запускается.

## 11. RBAC foundation — CURRENT

Canonical contract:

`docs/RBAC_PROCUREMENT.md`

- [~] RBAC foundation реализован в source и проходит pre-production audit/remediation.
- [x] Product role model согласована.
- [x] Capability model согласована.
- [x] Existing-role migration contract реализован.
- [x] OWNER singleton/recovery invariant реализован.
- [x] Добавлены ENGINEER / SENIOR_ENGINEER / MANAGER / ADMIN / OWNER.
- [x] Migration USER -> ENGINEER.
- [x] Runtime reconciliation configured recovery identity -> OWNER.
- [x] Оставшиеся ADMIN сохраняются как ADMIN.
- [x] Backend capability policy.
- [x] Audited role transitions.
- [x] ADMIN не может назначать ADMIN/OWNER.
- [x] OWNER может назначать ADMIN.
- [x] OWNER защищён от normal role/access mutation.
- [x] Warehouse authorization синхронизирован.
- [x] Catalog authorization синхронизирован.
- [x] Role-aware frontend navigation/actions.
- [x] PostgreSQL integration acceptance.
- [x] Frontend unit/browser acceptance.
- [~] Full CI acceptance повторяется после audit remediation.
- [x] Source migration head `b2c3d4e5f6a7`.
- [ ] Production RBAC maintenance cutover.

## 12. Procurement domain

После устойчивого RBAC foundation:

- [ ] Отдельный backend module `procurement`.
- [ ] ProcurementRequest.
- [ ] Immutable ProcurementRevision.
- [ ] Existing-item и proposed-item lines.
- [ ] Assigned Manager как responsibility, не ACL.
- [ ] Любой MANAGER может работать с любой активной закупкой.
- [ ] `Взять на себя`.
- [ ] `Передать менеджеру`.
- [ ] `Ожидает менеджера`.
- [ ] `Требует корректировки`.
- [ ] Mandatory correction comment.
- [ ] Structured manager alternative proposal.
- [ ] New revision после корректировки.
- [ ] `В закупке`.
- [ ] `На приёмке`.
- [ ] `Есть расхождения` без stock mutation.
- [ ] Создание catalog Item из proposed line только технической ролью.
- [ ] Receiving location selection.
- [ ] Double confirmation final acceptance.
- [ ] Atomic Warehouse RECEIPT.
- [ ] Exactly-one procurement -> receipt linkage.
- [ ] `Выполнена`.
- [ ] Immutable event/audit trail.
- [ ] Concurrency/state-transition protection.
- [ ] Telegram notifications + Mini App deep links.
- [ ] PostgreSQL integration acceptance.
- [ ] Role-specific browser E2E.
- [ ] Full CI acceptance.
- [ ] Real Telegram acceptance.

## 13. Procurement email delivery

После acceptance core procurement workflow:

- [ ] Microsoft Graph application integration.
- [ ] OAuth credentials через secret boundary.
- [ ] To / CC policy.
- [ ] HTML/text procurement message.
- [ ] Async delivery через outbox/worker semantics.
- [ ] Retry/dead-letter behavior.
- [ ] Email failure не откатывает business transaction.
- [ ] Production secret/runbook documentation.

## 14. Future product work

Не входит в текущий feature cycle без отдельного решения:

- partial procurement acceptance;
- supplier directory;
- invoices / OCR;
- ERP/accounting integration;
- dynamic custom roles;
- attachment storage;
- procurement price analytics.

Исторические решения и завершённые промежуточные изменения хранятся в
`docs/HISTORY.md`, а не размножаются как незакрытые текущие пункты roadmap.
