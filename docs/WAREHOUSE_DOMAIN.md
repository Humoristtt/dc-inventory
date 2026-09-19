# Warehouse Domain V2 — канонический контракт

Warehouse V2 использует количественный учёт. `Item` — номенклатурная позиция, не физический экземпляр. PostgreSQL immutable Movement/MovementLine journal является источником истории; остатки и custody — транзакционные projections, не самостоятельно редактируемые данные.

    StockBalance = Item × StorageLocation × positive quantity
    UserItemCustodyBalance = User × Item × positive quantity

Схема Warehouse V2 развёрнута и ранее принята в production. Последняя документированная production Procurement schema — `c3d4e5f6a7b8`; source Alembic head `a9c0d1e2f3a4` содержит более поздние DB invariants и **не** становится production schema без миграции. Current release acceptance: `docs/AUDIT_0_12_REMEDIATION.md`.

## Stock и custody

`StockBalance` хранит Item × Location → quantity. Сумма по локациям = общий остаток. Количество — положительное целое; zero rows удаляются, negative stock запрещён. Изменять остаток напрямую вне Warehouse service нельзя.

`actor_user_id` — исполнитель, `custody_user_id` — ответственный сотрудник. `UserItemCustodyBalance` = User × Item × positive quantity: ENGINEER/SENIOR_ENGINEER ISSUE увеличивает собственную custody, RETURN уменьшает и не может превысить её. ADMIN/OWNER складские ISSUE/RETURN являются административными и не создают personal custody. Нет current-holder конкретного физического экземпляра.

Custody и access lifecycle связаны: nonzero custody блокирует APPROVED → BLOCKED и переход на роль без custody. Access mutation и custody-changing movement сериализуются через row lock пользователя. Correction custody-bearing movement запрещён; REVERSAL наследует custody исходного движения. REVERSAL RETURN, увеличивающий custody, допустим только для APPROVED custody-capable user. Negative custody запрещён, zero custody rows удаляются.

## Локации и каталог

`StorageLocation`: stable machine code, display name, тип `WAREHOUSE`/`DATACENTER`, optional address, lifecycle `ACTIVE`/`ARCHIVED`. Архивирование с ненулевым stock запрещено. Item содержит versioned leaf-schema attributes, но **не** текущий остаток. Archived Item запрещает новый RECEIPT/ISSUE, разрешает допустимые RETURN/TRANSFER/WRITE_OFF/CORRECTION/REVERSAL существующего stock.

## Типы движений

- RECEIPT: внешний источник → location.
- ISSUE: location → внешний мир; custody при employee operation.
- RETURN: внешний мир → location; custody при employee operation.
- TRANSFER: между различными locations.
- WRITE_OFF: location → внешний мир.
- CORRECTION: linked adjustment при соблюдении business invariants.
- REVERSAL: полное компенсирующее движение исходного movement.

`MovementLine` хранит immutable Item snapshot и positive quantity. Изменение/удаление journal через обычный API запрещено. Final RECEIPT, указанный как `ProcurementRequest.final_movement_id`, нельзя корректировать или разворачивать generic Warehouse CORRECTION/REVERSAL: source migration `d4e5f6a7b8c9` и последующие до `a9c0d1e2f3a4` усиливают application/DB safeguards. Completed procurement требует отдельного business workflow для отмены.

## Атомарность и блокировки

Movement header/lines, stock/custody projections, outbox intent и idempotency фиксируются одной PostgreSQL transaction. Порядок: normalize client request ID → advisory idempotency lock → fingerprint/replay check → lock original movement при необходимости → custody user/access, locations, Items → ordered stock/custody balance locks → insert movement/lines, apply deltas, enqueue outbox → COMMIT. Если шаг падает, побочные изменения в БД откатываются. Replay идентичного actor/request/payload возвращает исходный Movement; иной fingerprint → conflict.

Journal pagination не блокирует writers глобальным snapshot lock. Первая страница фиксирует MVCC snapshot (`pg_current_snapshot()`) и server timestamp; последующие используют HMAC-signed cursor, привязанный к requester/filters/snapshot. `pg_visible_in_snapshot(...)` исключает движения, невидимые в первом snapshot. Raw `snapshot_at`/`before_journal_seq` от клиента не являются публичным contract.

## Доступ по ролям

ENGINEER читает каталог/stock/locations, собственную actor-history и выполняет ISSUE, RETURN, RECEIPT существующей позиции, TRANSFER. SENIOR_ENGINEER дополнительно видит общий journal, управляет каталогом и проводит technical procurement acceptance, но не получает `inventory.admin`. MANAGER читает catalog/stock/locations и procurement, без warehouse mutations или общего journal. ADMIN/OWNER администрируют catalog/locations, все разрешённые Warehouse movements, включая WRITE_OFF/CORRECTION/REVERSAL. Capabilities проверяются backend, frontend visibility — только UX. Актуальная матрица: `docs/RBAC_PROCUREMENT.md`.

## Уведомления

Каждый новый ISSUE ставит Telegram notification intent в outbox в той же транзакции, что Movement; dedupe key от movement предотвращает duplicate enqueue при idempotent replay. Delivery worker выполняет lease/retry/DEAD. Telegram/Gateway side effect не атомарен с PostgreSQL: возможна повторная внешняя доставка после lost response; exactly-once не заявляется.

## Reconciliation и recovery

`backend/scripts/reconcile_inventory_projections.sql` — read-only сверка stock и custody с immutable Movement/MovementLine. Норма — **zero rows**. При drift остановить regular mutations, сохранить evidence/backup, расследовать; автоматического rebuild/repair нет. После миграций, restore и risky warehouse operations reconciliation обязательна.

Для восстановления SQL обязан соответствовать restored schema и извлекается из exact backend image, зафиксированного в backup manifest; не берётся вслепую из более нового Git checkout.

## Исключённый scope

Warehouse V2 не содержит active SERIAL accounting mode, `InventoryUnit`, serial/WWN physical-unit lifecycle, current holder отдельного экземпляра, `/api/inventory/units` или отдельного `/api/inventory/mine` и user-facing «Моё оборудование». Это **не** отменяет агрегированную backend custody projection. Старый physical-unit contract может встречаться только в historical migrations, downgrade/regression tests и `docs/HISTORY.md` как история.

Regular mutation gate по последней production проверке остаётся `REAL_INVENTORY_MUTATIONS_ENABLED=false`. Initial production inventory bootstrap уже был выполнен one-shot и повторяться не должен.
