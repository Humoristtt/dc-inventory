# Warehouse Domain V2

Этот документ является каноническим описанием складской модели Spikatel Inventory.

## Основной принцип

Warehouse V2 использует количественный учёт без модели индивидуальных физических
экземпляров.

Item является номенклатурной позицией, а не physical unit.

Система ведёт две транзакционные current-state projections:

    StockBalance = Item × StorageLocation × positive quantity
    UserItemCustodyBalance = User × Item × positive quantity

`actor_user_id` отвечает на вопрос «кто выполнил операцию».

`custody_user_id` отвечает на вопрос «за каким USER сейчас числится количество
оборудования».

Actor и custody — разные понятия.

## Складской остаток

Складская проекция:

    Item × StorageLocation → quantity

Правила:

- quantity — положительное целое число;
- строки с нулевым остатком не хранятся;
- отрицательный остаток запрещён;
- общий складской остаток Item равен сумме остатков по локациям;
- `stock_balances` является транзакционной проекцией immutable journal;
- прямое редактирование остатка не допускается.

## Custody

Персональная custody-проекция:

    User × Item → quantity

Правила:

- custody существует только для ENGINEER / SENIOR_ENGINEER;
- ENGINEER / SENIOR_ENGINEER ISSUE увеличивает custody;
- ENGINEER / SENIOR_ENGINEER RETURN уменьшает custody;
- custody-capable пользователь не может вернуть больше, чем числится в его custody;
- ADMIN / OWNER ISSUE/RETURN являются административными складскими движениями
  и не создают персональную custody;
- zero custody rows не хранятся;
- negative custody запрещён;
- correction custody-bearing movement запрещён;
- reversal наследует custody исходного movement;
- reversal RETURN, который снова увеличивает custody, допустим только для
  APPROVED custody-capable пользователя;
- блокировка пользователя с ненулевым custody запрещена fail-closed;
- изменение access-state и custody-changing movement сериализуются по row lock
  пользователя.

Custody является агрегированной количественной проекцией. Она не возвращает
legacy модель InventoryUnit, serial/WWN lifecycle или current holder конкретного
физического экземпляра.

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

## Transaction model

Movement, MovementLine, stock projection, custody projection и transactional
outbox effects фиксируются одной PostgreSQL transaction.

Locking используется для:

- idempotency key;
- custody user access boundary;
- original movement context;
- locations;
- Items;
- stock balances;
- custody balances.

Journal feed не блокирует warehouse writers глобальным snapshot lock.
Первая страница фиксирует PostgreSQL MVCC snapshot через
`pg_current_snapshot()` и server timestamp. Последующие страницы используют
HMAC-signed opaque cursor, привязанный к requester, фильтрам и исходному
snapshot. `pg_visible_in_snapshot(...)` не допускает в feed transaction,
которая была невидима при фиксации первой страницы, даже если она commit-нулась
между страницами. Raw client-controlled `snapshot_at` и `before_journal_seq`
не являются публичным pagination contract.

## Idempotency

Каждая mutation использует `client_request_id`.

Повтор идентичного запроса того же actor возвращает существующее движение.
Повтор того же ключа с другим payload возвращает conflict.

Fingerprint включает custody context.

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

ENGINEER:

- browse/search/filter catalog;
- просмотр stock и locations;
- просмотр собственной actor-history;
- ISSUE;
- RETURN;
- RECEIPT существующей номенклатуры;
- TRANSFER.

ENGINEER ISSUE/RETURN используют custody самого ENGINEER.

SENIOR_ENGINEER:

- все обычные warehouse operations ENGINEER;
- общий movement journal и employee filter;
- catalog create/edit/archive;
- без `inventory.admin`.

MANAGER:

- read-only catalog / stock / locations;
- warehouse mutations запрещены;
- movement journal недоступен.

ADMIN / OWNER:

- общий movement journal и employee filter;
- Location administration;
- catalog administration;
- RECEIPT / ISSUE / RETURN / TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

ADMIN / OWNER warehouse movement не назначает custody автоматически.

## Access lifecycle

APPROVED пользователь может выполнять только warehouse mutations, разрешённые его capabilities.

Переход APPROVED → BLOCKED запрещён, пока у пользователя существует ненулевой
`UserItemCustodyBalance`.

Это правило синхронизировано с concurrent custody-changing movement через lock
той же строки `users`.

## Уведомления

Каждый новый ISSUE ставит Telegram-уведомление ADMIN в transactional outbox в той
же DB-транзакции, что и movement.

Dedupe строится от movement id, поэтому idempotent replay не создаёт второе
уведомление.

## Reconciliation

`backend/scripts/reconcile_inventory_projections.sql` пересчитывает ожидаемые:

- stock balances по Item × Location;
- custody balances по User × Item.

Обе проекции сверяются с immutable journal.

Нормальный результат reconciliation — zero rows.

При recovery reconciliation SQL обязан соответствовать restored schema version
и берётся из exact backend image, записанного в backup manifest.

## Отсутствующая physical-unit модель

Warehouse V2 не использует в active schema/API/UI:

- SERIAL accounting mode;
- InventoryUnit;
- serial/WWN physical-unit lifecycle;
- current holder конкретного физического экземпляра;
- `/api/inventory/units`.

Отдельного product UI «Моё оборудование» и отдельного `/api/inventory/mine`
сейчас нет. Это не отменяет backend custody projection, используемую для
целостности ISSUE/RETURN и access lifecycle.

Historical physical-unit model допустима только в historical migrations,
downgrade/regression tests и `docs/HISTORY.md`.
