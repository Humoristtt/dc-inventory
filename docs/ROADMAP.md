# План разработки Spikatel Inventory

Канонический roadmap после перехода на Warehouse Domain V2.

Статусы:

- [x] завершено;
- [~] текущая приёмка;
- [ ] будущая работа.

Последнее обновление: 2026-09-11.

## 1. Базовая платформа

- [x] Telegram Mini App.
- [x] FastAPI backend.
- [x] PostgreSQL.
- [x] Docker Compose production-shaped runtime.
- [x] Cloudflare / HTTPS production path.
- [x] Telegram initData server-side validation.
- [x] HttpOnly server session.
- [x] ADMIN / USER access model.
- [x] Access request approve/reject через Telegram.
- [x] Transactional notification outbox.
- [x] Fail-closed mutation gate.

## 2. Warehouse Domain V2

- [x] Quantity-only inventory.
- [x] Удалена active physical-unit model.
- [x] Удалена legacy physical-unit holder model.
- [x] Actor операции отделён от custody пользователя.
- [x] UserItemCustodyBalance = User × Item × positive quantity.
- [x] USER RETURN ограничен фактическим custody balance.
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

USER:

- [x] Browse/search/filter catalog.
- [x] Read stock.
- [x] Read own actor history.
- [x] ISSUE.
- [x] RETURN.

ADMIN:

- [x] Common movement journal.
- [x] Employee history filter.
- [x] Location CRUD/archive.
- [x] Item CRUD/archive.
- [x] RECEIPT.
- [x] TRANSFER.
- [x] WRITE_OFF.
- [x] Correction/reversal workflow.

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
- [x] USER Взять.
- [x] USER Вернуть.
- [x] ADMIN Переместить.
- [x] ADMIN Приход.
- [x] ADMIN Списать.
- [x] Movement journal.
- [x] Employee filter для ADMIN.
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

- [x] ADMIN получает notification на ISSUE.
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
- [x] Current migration head `f8a9b0c1d2e3`.
- [x] External authoritative workbook contract.
- [x] Fail-closed production one-shot bootstrap path.
- [x] Empty-domain production preflight.
- [x] Fresh verified pre-import off-VM backup.
- [x] Initial production inventory bootstrap.
- [x] Post-import DB/count/quantity verification.
- [x] Post-import projection reconciliation zero drift.
- [x] Fresh verified post-import off-VM backup.
- [x] Real Telegram visual acceptance.

## 10. Current stabilization / closeout

Текущая фаза не добавляет новый product domain. Цель — получить чистый,
документированный и независимо проверенный production baseline перед следующим
feature cycle.

- [x] Frontend startup/navigation performance pass:
  - [x] определить фактический startup/catalog critical path;
  - [x] сохранить backend authorization как security boundary;
  - [x] добавить current-route preload параллельно startup auth;
  - [x] сохранить lazy-route и initial-bundle contract;
  - [x] убрать category-detail -> items serial frontend waterfall;
  - [x] добавить family child-metadata prefetch;
  - [x] добавить immediate item-detail preview с server revalidation;
  - [x] добавить deterministic slow/pending-network browser regressions;
  - [x] пройти final full frontend/CI acceptance;
  - [x] пройти real Telegram acceptance после deployment.
- [x] UX consistency pass после performance acceptance завершён:
  implementation/local acceptance, PR #58, required CI и production cutover
  выполнены; production baseline переведён на
  `ffe099000b78b775c5a04e48c3170d57fb2884ed`.
  Последующий real Telegram desktop review выявил отдельные follow-up findings
  по typography/form consistency, вынесенные в новый change set.

- [x] Canonical documentation reconciled with accepted production state.
- [x] Очистить merged Git branches; после closeout оставить только `main`.
- [x] Очистить production VM от временных bootstrap/build/test artifacts,
      сохранив operational state и намеренные rollback/recovery artifacts.
- [x] Очистить Mac development environment от obsolete branches/worktrees,
      temporary archives, caches и disposable Docker resources.
- [x] Выполнить independent full source/security/runtime/data audit на clean baseline.
- [x] Исправить findings текущего audit до технически чистого baseline.
- [x] Синхронизировать custody/access lifecycle и запретить BLOCKED при outstanding custody.
- [x] Сделать restore reconciliation schema-version-safe через exact backend image.
- [x] Сделать movement feed snapshot commit-stable при concurrent journal writers.
- [x] Добавить narrow safe HTTP mapping известных custody DB-trigger violations.
- [x] Выкатить accepted audit baseline
      `c32df46426125d16cf8a1dc490a36706eaa9a50b` в production.
- [x] Мигрировать production до `f8a9b0c1d2e3` и подтвердить zero-drift reconciliation.
- [x] Выполнить post-deploy verified backup, external smoke и real Telegram visual acceptance.
- [x] Завершить production VM / Git / local hygiene после audit deployment.
- [x] Зафиксировать пользовательский список minor UX corrections.
- [x] Выполнить minor UX remediation отдельной веткой:
  - [x] унифицировать header/kicker rhythm и bottom navigation;
  - [x] сделать stock availability strip однозначным и полноширинным;
  - [x] улучшить category description/readability;
  - [x] добавить one-click quick sort с category-aware default для трансиверов;
  - [x] сохранить полный sort fallback и URL round-trip semantics;
  - [x] сделать filter sheet компактным без уменьшения touch targets;
  - [x] привести compound reach presentation к middle-dot separators;
  - [x] сделать Locations editor responsive bottom-sheet/modal;
  - [x] закрыть role-loss lifecycle и удалить dead/duplicate CSS.
- [x] Завершить delivery предыдущего UX consistency pass:
  - [x] local unit/typecheck/lint/build acceptance;
  - [x] canonical frontend Playwright acceptance;
  - [x] GitHub PR #58 / required CI acceptance;
  - [x] production deploy/provenance/health acceptance;
  - [x] real Telegram visual review.
- [~] Follow-up typography/form consistency pass после real Telegram review:
  - [x] ввести shared typography scale в design tokens;
  - [x] ввести shared responsive form-control geometry;
  - [x] сохранить desktop как текущий visual acceptance target,
        не ломая tablet/mobile responsive contract;
  - [x] увеличить readability equipment cards;
  - [x] перебалансировать detail-page typography;
  - [x] унифицировать detail/create/edit page header pattern;
  - [x] выровнять input/select geometry в Locations editor;
  - [x] привести Add/Edit equipment controls к общей высоте;
  - [x] добавить browser regression contracts для typography/form geometry;
  - [x] local unit/typecheck/lint/build acceptance;
  - [x] canonical Warehouse Playwright acceptance;
  - [x] GitHub PR/CI acceptance;
  - [x] production deploy/provenance/health acceptance;
  - [~] real Telegram visual acceptance выявил follow-up design-system findings.
- [~] Frontend design-system architecture refactor перед следующим production cutover:
  - [x] провести source audit текущего visual ownership;
  - [x] зафиксировать canonical design-system contract;
  - [x] создать `frontend/src/shared/ui` как единственный shared visual layer;
  - [x] заменить независимые page headers единым `PageHeader`;
  - [ ] унифицировать Button / form-field / single-line control contracts;
  - [x] удалить shared toolbar/header/control rules из feature CSS;
  - [ ] удалить obsolete cascade refinements и duplicate geometry;
  - [x] добавить `npm run check:design-system`;
  - [ ] добавить browser regressions общей header/control geometry;
  - [ ] пройти unit/typecheck/lint/build/E2E;
  - [ ] провести финальный source audit на отсутствие второго design-system layer;
  - [ ] GitHub PR / required CI acceptance;
  - [ ] production deploy/provenance/health acceptance;
  - [ ] real Telegram desktop acceptance.

- [ ] Принять explicit operational decision по normal warehouse mutations.

До последнего пункта regular mutation gate остаётся:

    REAL_INVENTORY_MUTATIONS_ENABLED=false

Initial bootstrap уже выполнен и повторно не запускается.

## 11. Future procurement workflow

Этот блок является следующим подтверждённым product-направлением после
стабилизации текущего warehouse baseline.

- [ ] Purchasing manager role/capability.
- [ ] Формирование списка «что необходимо купить».
- [ ] Requested quantity.
- [ ] Обоснование / комментарий.
- [ ] Экспорт / отправка списка закупщику.
- [ ] Procurement request statuses.
- [ ] Заказано.
- [ ] Частично доставлено.
- [ ] Доставлено.
- [ ] Отменено.
- [ ] Связь поступления товара с procurement request.
- [ ] Уведомления о смене procurement status.
- [ ] Дополнительные approval roles/workflow при необходимости.

Новые feature-направления сверх этого блока добавляются в roadmap только после
закрытия current stabilization/audit phase.

## 12. Изменённые решения

Ранее проект содержал модель индивидуальных physical units и персонального
владения оборудованием.

Она признана избыточной для фактического складского процесса и удалена из active
schema/API/UI.

Историческое развитие сохраняется в docs/HISTORY.md, старых migrations и
migration regression tests.

## Catalog functional follow-up — 2026-09-11

- [x] server-side сортировка каталога по `speed`;
- [x] быстрые sort chips `Наличие / Скорость` для трансиверов;
- [x] strict separation: ordinary Ethernet/FC `< 2000 м`,
  `Дальние >= 2000 м`;
- [x] catalog и inventory equipment scopes используют одинаковую границу;
- [x] backend/frontend regression coverage;
- [x] PostgreSQL integration acceptance;
- [x] canonical browser E2E acceptance;
- [ ] PR/required CI;
- [ ] production deploy + real Telegram acceptance.

## Post-PR60 Telegram acceptance — 2026-09-11

- [x] убрать native англоязычную browser validation из catalog form;
- [x] вернуть More/category secondary copy в shared typography role;
- [x] нормализовать DECIMAL presentation (`10.0000` → `10`,
  `1.5000000000` → `1,5`) без изменения данных;
- [x] page-local search/filter/sort state не создаёт history steps для Back;
- [x] server-side search relevance: strongest match first;
- [x] canonical production-shaped E2E acceptance;
- [ ] PR/required CI;
- [ ] production deploy + повторная real Telegram acceptance.
