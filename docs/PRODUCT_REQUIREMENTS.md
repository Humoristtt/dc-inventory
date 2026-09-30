# Функциональные требования Spikatel Inventory

Этот документ фиксирует фактически реализованный продуктовый контракт. Технические детали находятся в профильных domain-документах.

## 1. Назначение

Spikatel Inventory предназначен для внутреннего количественного учёта оборудования и материалов ЦОД:

- ведение номенклатуры;
- учёт количества по местам хранения;
- учёт количества, закреплённого за сотрудниками;
- неизменяемая история складских операций;
- процесс закупки от заявки до технической приёмки;
- Telegram-based authentication/access workflow;
- служебные уведомления.

## 2. Единица учёта

`Item` — тип/номенклатурная позиция. Количество хранится отдельно.

Система не является CMDB отдельных физических экземпляров и не обещает serial/WWN lifecycle, asset depreciation, topology/DCIM, автоматическую синхронизацию с внешними инфраструктурными системами или бухгалтерский учёт.

## 3. Каталог

Пользователь должен иметь возможность просматривать и искать позиции, переходить по fixed family/leaf taxonomy, фильтровать по availability и category attributes, сортировать по поддерживаемым полям, видеть технические характеристики и остаток.

Пользователь с `catalog.manage` может создавать/изменять номенклатуру и производителей. `catalog.archive` разрешает архивирование/возврат из архива. `catalog.delete_unused` разрешает физическое удаление только позиции, которая не участвует в защищённой истории/связях.

Identity позиции определяется нормализованными canonical fields и technical attributes.

## 4. Склад

Поддерживаются `RECEIPT`, `ISSUE`, `RETURN`, `TRANSFER`, `WRITE_OFF`, `CORRECTION`, `REVERSAL`.

Обязательные свойства:

- movement содержит одну или несколько положительных lines;
- stock/custody никогда не становится отрицательным;
- source/destination/custody semantics зависят от movement type;
- один logical retry не создаёт второе движение;
- history append-only;
- correction/reversal создаёт новый journal event;
- projection согласуется с history.

`StorageLocation` имеет тип `WAREHOUSE` или `DATACENTER`, status `ACTIVE/ARCHIVED`.

## 5. Custody

ISSUE закрепляет количество за сотрудником; RETURN уменьшает его custody. Actor операции и custody holder — разные сущности.

Пользователь с положительным custody не должен быть переведён в access/role state, несовместимый с holder eligibility.

## 6. Роли и доступ

Поддерживаются `ENGINEER`, `SENIOR_ENGINEER`, `MANAGER`, `ADMIN`, `OWNER`.

Access status: `PENDING`, `APPROVED`, `REJECTED`, `BLOCKED`.

Role не заменяет access status. Полная матрица — [ACCESS_AND_RBAC.md](ACCESS_AND_RBAC.md).

## 7. Закупки

Закупка содержит initiator, assigned manager, current status, immutable revisions, lines, immutable events, optional proposed-line bindings к Catalog и final warehouse movement после завершения.

Line может быть `EXISTING_ITEM` или `PROPOSED_ITEM`.

Workflow:

```text
AGREEMENT_PENDING_MANAGER
   ├── manager accepts ─────────► PURCHASING
   └── correction requested ────► AGREEMENT_REVISION_REQUIRED
                                      │ new revision
                                      ▼
                               AGREEMENT_PENDING_MANAGER

PURCHASING ─► AWAITING_ACCEPTANCE
                    │
                    ├── discrepancy/correction ─► AGREEMENT_REVISION_REQUIRED
                    └── technical acceptance ───► COMPLETED
```

Manager reassignment разрешён только для active request и использует stale-assignment protection.

## 8. Technical acceptance

До completion proposed lines должны быть bound к Catalog Item; Items должны быть ACTIVE; identity signature должна совпадать с approved line; aggregated quantity и destination location должны быть допустимы; actor должен иметь `procurement.accept`.

Completion атомарно создаёт Warehouse `RECEIPT`, записывает `final_movement_id`, меняет Procurement status на `COMPLETED`, пишет immutable event и создаёт notification intents.

Если транзакция падает, Procurement и Warehouse не расходятся.

## 9. Уведомления

Предметная транзакция записывает outbox intent. Внешний Telegram/Graph вызов выполняет worker после commit.

Telegram — основной delivery channel. Email через Microsoft Graph — optional и default-off.

## 10. Frontend

Интерфейс должен:

- работать как Telegram Mini App;
- корректно использовать safe area и BackButton;
- оставлять route pages lazy-loaded;
- не переносить security boundary в browser;
- показывать loading/error/retry states;
- не допускать двойную mutation из-за повторного клика;
- хранить server state в React Query без второго глобального server-state store.

## 11. Operational safety

По умолчанию:

```text
REAL_INVENTORY_MUTATIONS_ENABLED=false
EMAIL_DELIVERY_ENABLED=false
```

## 12. Non-goals

Не заявлены exactly-once внешняя доставка, automatic production deployment/restore, runtime schema construction UI, serial-number CMDB, offline-first frontend и multi-region active-active PostgreSQL.
