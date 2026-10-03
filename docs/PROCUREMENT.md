# Procurement domain

Procurement ведёт бизнес-процесс закупки отдельно от Warehouse. До финальной технической приёмки заявка не меняет складские остатки.

## 1. Сущности

**ProcurementRequest** — mutable header: request_number, status, initiator, assigned manager, creation idempotency key/fingerprint, `current_revision_id`, `state_version`, optional `final_movement_id`, timestamps.

**ProcurementRevision** — immutable опубликованная редакция.

**ProcurementRevisionLine** — immutable line внутри revision.

**ProcurementLineCatalogBinding** — append-only binding proposed line к Item.

**ProcurementEvent** — immutable audit/business event.

**EmailOutbox** — optional delivery intent.

## 2. Line types

### EXISTING_ITEM

Содержит `catalog_item_id` и snapshot согласованной identity.

### PROPOSED_ITEM

Хранит display snapshot и `expected_identity_signature`. Каталожная карточка может быть создана/связана позже.

Approved revision никогда не пересчитывается из изменившегося Catalog.

## 3. Status machine

Statuses:

- `AGREEMENT_PENDING_MANAGER`;
- `AGREEMENT_REVISION_REQUIRED`;
- `PURCHASING`;
- `AWAITING_ACCEPTANCE`;
- `COMPLETED`.

Основной flow:

```text
create
  ▼
AGREEMENT_PENDING_MANAGER
  │
  ├─ manager_accept ─────────────► PURCHASING
  │                                  │
  │                                  └─ transfer_to_acceptance
  │                                              ▼
  │                                    AWAITING_ACCEPTANCE
  │                                              │
  │                                              └─ complete_acceptance
  │                                                         ▼
  │                                                     COMPLETED
  │
  └─ return_for_correction ──────► AGREEMENT_REVISION_REQUIRED
                                      │
                                      └─ initiator submit_revision
                                                 ▼
                                      AGREEMENT_PENDING_MANAGER
```

Correction также допускается из acceptance path согласно server policy. Discrepancy создаёт event/notification и не подменяет revision.

## 4. Capabilities

- `procurement.create` — создание request и revision инициатором;
- `procurement.manage` — manager accept/correction/assignment/transfer;
- `procurement.accept` — technical binding/discrepancy/completion;
- `procurement.read` — read/list/detail.

Точная role mapping: [ACCESS_AND_RBAC.md](ACCESS_AND_RBAC.md).

## 5. Optimistic state contract

Каждая mutation, где важен текущий state, передаёт ожидаемые `state_version`, `current_revision_id`; для reassignment — current assigned manager.

Server берёт lock и отклоняет stale command вместо молчаливого применения поверх более нового state.

## 6. Action idempotency

Business mutation содержит `client_request_id`.

Сервер связывает key с request, actor, event type/action и fingerprint command.

Lost-response retry с тем же logical intent возвращает уже выполненный результат. Повтор key с другим payload — conflict.

Frontend сохраняет idempotency key на время retry одного и того же intent.

## 7. Revisions

Revision после публикации immutable: header, lines, snapshots.

New correction создаёт новую revision, а не переписывает предыдущую.

DB triggers защищают late line INSERT и mutation/truncate immutable revision data. `current_revision_id` валидируется deferred DB trigger.

## 8. Manager assignment

Assigned manager — business responsibility.

Take ownership / transfer:

1. lock request;
2. verify expected current manager;
3. verify active request;
4. verify target has manager capability;
5. update assigned manager + state version;
6. append immutable event;
7. enqueue notification.

Identity role/access mutation запрещается, если пользователь несёт active Procurement responsibility, несовместимую с новым состоянием.

## 9. Binding proposed line

`bind_line` проверяет:

- request не COMPLETED;
- line относится к current revision;
- line type PROPOSED_ITEM;
- binding ещё отсутствует;
- target Item существует и ACTIVE;
- Item `identity_signature` совпадает с line `expected_identity_signature`;
- aggregated quantity остаётся в допустимом диапазоне.

`create_and_bind_line` делает Catalog create + binding в одной transaction и требует одновременно `procurement.accept` и `catalog.manage`.

## 10. Technical acceptance

Completion выполняется под request lock.

Порядок:

1. проверить expected state/revision и idempotency;
2. повторно проверить `procurement.accept`;
3. получить current revision;
4. определить итоговый Item каждой line;
5. заблокировать Items в детерминированном порядке;
6. убедиться, что Items ACTIVE;
7. перепроверить identity signature;
8. агрегировать количества одинакового Item;
9. создать Warehouse RECEIPT;
10. записать `final_movement_id`;
11. перевести status в COMPLETED;
12. записать completion event;
13. enqueue notifications;
14. commit на API boundary.

Warehouse и Procurement не могут успешно commit-иться по отдельности.

## 11. Защита финального RECEIPT

Final movement связан с Procurement DB invariant.

Generic Warehouse reversal/correction такого receipt запрещён. Если бизнесу понадобится отмена завершённой закупки, это должен быть отдельный cross-domain use case, который меняет обе стороны согласованно.

## 12. Notifications и email

Business events могут enqueue Telegram notifications в той же DB transaction.

Email endpoint создаёт `EmailOutbox`. Реальная Graph delivery выполняется отдельным worker и может быть полностью выключена.

## 13. Query model

List views:

- `my`;
- `active`;
- `history`.

Pagination bounded. Manager lookup и catalog binding lookup также paginated/searchable.

Backend имеет отдельные real-PostgreSQL query scalability regressions.

## 14. Database invariants

PostgreSQL защищает:

- append-only revisions;
- append-only revision lines;
- sealed revision line insertion;
- append-only events;
- append-only bindings;
- current revision ownership;
- event/revision consistency;
- final movement binding;
- historical identity semantics.


## 15. Implementation boundaries

`app.modules.procurement.service` — публичный façade. Основная реализация распределена по owning modules:

- `workflow.py` — create, manager decisions, revisions, assignment и transfer lifecycle;
- `acceptance.py` — line binding, discrepancy и final technical acceptance;
- `queries.py` — list/detail/manager reads;
- `lines.py` — preparation и aggregate validation procurement lines;
- `mutation_support.py` — locks, expected-state/idempotency checks, events и transitions support;
- `actors.py`, `actions.py`, `notifications.py`, `domain.py` — соответствующие вспомогательные boundaries.

Тесты, которым требуется monkeypatch execution dependency, должны подменять символ в owning module, где он реально вызывается, а не исторический re-export façade.
