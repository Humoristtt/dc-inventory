# План разработки Spikatel Inventory

Канонический roadmap после перехода на Warehouse Domain V2.

Статусы:

- [x] завершено;
- [~] текущая приёмка;
- [ ] будущая работа.

Последнее обновление: 2026-09-08.

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
- [x] Удалены персональные holder/custody semantics.
- [x] Пользователь является только movement actor.
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
- [x] Current migration head `c5d6e7f8a9b0`.
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

- [x] Canonical documentation reconciled with accepted production state.
- [x] Очистить merged Git branches; после closeout оставить только `main`.
- [x] Очистить production VM от временных bootstrap/build/test artifacts,
      сохранив operational state и намеренные rollback/recovery artifacts.
- [x] Очистить Mac development environment от obsolete branches/worktrees,
      temporary archives, caches и disposable Docker resources.
- [~] Выполнить independent full source/security/runtime/data audit на clean baseline.
- [ ] Исправить найденные P0/P1 blockers отдельными change sets.
- [ ] Зафиксировать пользовательский список minor UX corrections.
- [ ] Выполнить minor UX remediation отдельной веткой.
- [ ] Повторить final affected/full acceptance после UX fixes.
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
