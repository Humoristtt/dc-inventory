# Warehouse Domain V2

Этот документ является каноническим описанием складской модели Spikatel Inventory.

## Основной принцип

Warehouse V2 использует только количественный учёт.

Пользователь является только actor движения — человеком, который выполнил операцию
в системе. Система не хранит и не вычисляет персональный остаток оборудования у
сотрудника.

Если сотрудник взял 20 единиц, а затем вернул 16, журнал содержит два факта:

- ISSUE 20;
- RETURN 16.

Состояние вида «у сотрудника осталось 4» из этого не выводится.

## Остаток

Единственная текущая складская проекция:

Item × StorageLocation → quantity

Правила:

- quantity — положительное целое число;
- строки с нулевым остатком не хранятся;
- отрицательный остаток запрещён;
- общий остаток Item равен сумме остатков по локациям;
- stock_balances является транзакционной проекцией immutable journal;
- прямое редактирование остатка не допускается.

## Локации

StorageLocation содержит:

- stable machine code;
- отображаемое имя;
- тип WAREHOUSE или DATACENTER;
- optional свободный address;
- lifecycle ACTIVE / ARCHIVED.

Архивировать локацию с ненулевым остатком нельзя.

## Движения

Поддерживаются:

- RECEIPT: внешний источник → location;
- ISSUE: location → внешний мир;
- RETURN: внешний мир → location;
- TRANSFER: location → location;
- WRITE_OFF: location → внешний мир;
- CORRECTION: linked исправляющее движение;
- REVERSAL: полное компенсирующее движение исходного movement.

Для TRANSFER source и destination должны различаться.

Movement хранит immutable snapshots actor, location и Item identity.
Исторические движения не редактируются и не удаляются обычным API.

## Idempotency

Каждая mutation использует client_request_id.

Повтор идентичного запроса того же actor возвращает существующее движение.
Повтор того же ключа с другим payload возвращает conflict.

## Archived Item

Для архивированного Item запрещены:

- RECEIPT;
- ISSUE.

Разрешены для завершения существующего складского состояния:

- RETURN;
- TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

## Роли

USER:

- browse/search/filter catalog;
- просмотр stock;
- просмотр собственной actor-history;
- ISSUE;
- RETURN.

ADMIN:

- всё доступное USER;
- общий movement journal;
- фильтр по employee;
- Location CRUD/archive;
- Item CRUD/archive;
- RECEIPT;
- TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

## Уведомления

Каждый новый ISSUE ставит Telegram-уведомление ADMIN в transactional outbox в той
же DB-транзакции, что и movement.

Dedupe строится от movement id, поэтому idempotent replay не создаёт второе
уведомление.

## Reconciliation

backend/scripts/reconcile_inventory_projections.sql пересчитывает ожидаемый
остаток из immutable journal и сравнивает его со stock_balances.

Нормальный результат reconciliation — zero rows.

## Удалённая модель

Warehouse V2 не использует в active schema/API/UI:

- SERIAL accounting mode;
- InventoryUnit;
- serial/WWN physical-unit lifecycle;
- персональные holder/current-holder balances;
- custody;
- экран «Моё оборудование»;
- /api/inventory/mine;
- /api/inventory/units.

Эти термины допустимы только в historical migrations, downgrade/regression tests
и docs/HISTORY.md.
