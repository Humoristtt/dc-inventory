# Warehouse domain

Warehouse — неизменяемый журнал количественных операций плюс две производные проекции: остаток по локациям и custody по сотрудникам.

## 1. Основные сущности

**Location**: code, normalized_code, name, optional address, type `WAREHOUSE | DATACENTER`, status `ACTIVE | ARCHIVED`.

**Movement**: monotonic `journal_seq`, movement type, actor, optional custody user, source/destination, optional original movement, `client_request_id`, request fingerprint, snapshots и occurred_at.

**MovementLine**: line_no, item_id, positive quantity, item/manufacturer/model snapshots.

**StockBalance**: projection `Item × Location → positive quantity`.

**UserItemCustodyBalance**: projection `User × Item → positive quantity`.

Нулевая projection row не нужна.

## 2. Movement types

| Type | Смысл |
|---|---|
| `RECEIPT` | поступление в location |
| `ISSUE` | выдача со склада в custody |
| `RETURN` | возврат из custody в location |
| `TRANSFER` | перемещение location → location |
| `WRITE_OFF` | списание из location |
| `CORRECTION` | контролируемая корректирующая операция |
| `REVERSAL` | отдельное обратное движение к допустимому original |

API ограничивает non-admin movement types для обычного `inventory.operate`. Административные типы требуют `inventory.admin`.

## 3. Journal invariant

`movements` и `movement_lines` append-only.

Обычный runtime role не получает UPDATE/DELETE этих таблиц. PostgreSQL triggers дополнительно отвергают mutation/truncate history.

Исправление ошибки — новое движение, а не изменение старого.

## 4. Projection invariant

`StockBalance` и `UserItemCustodyBalance` не редактируются обычным ORM DML.

Runtime:

1. вставляет journal rows;
2. вызывает `public.refresh_warehouse_projection(movement_id, item_id)`;
3. функция SECURITY DEFINER вычисляет projection из journal;
4. caller остаётся без broad DML privileges на projection tables.

Reconciliation SQL независимо пересчитывает ожидаемое состояние и ищет drift.

## 5. Lock order

Создание movement следует детерминированному порядку:

```text
idempotency/request context
→ custody User (если нужен)
→ original movement context (если нужен)
→ locations по стабильному порядку
→ items по стабильному UUID порядку
→ journal/projection writes
```

Original movement serialization использует advisory transaction lock вместо UPDATE row lock, потому что history row immutable и runtime UPDATE запрещён.

Lock order нельзя менять локальным refactor без отдельной concurrency regression.

## 6. Idempotency

Ключ логической операции: actor_user_id + `client_request_id`.

Fingerprint включает canonical movement semantics и lines.

Повтор с тем же key/fingerprint возвращает существующий logical result. Тот же key с другим fingerprint — conflict.

## 7. Stock validation

Перед записью проверяются source/destination existence/status, разные endpoints transfer, Item existence/status, отсутствие duplicate Item lines, достаточный source stock и допустимая quantity.

PostgreSQL projection также не допускает отрицательное состояние.

## 8. Custody

Для custody movement target User блокируется и должен иметь допустимую role и `APPROVED` access status.

ISSUE увеличивает custody; RETURN уменьшает. RETURN больше текущего custody запрещён.

Identity management отдельно проверяет outstanding custody перед role/access change/reset.

## 9. Corrections и reversal

Correction/reversal имеют отдельную validation policy.

Reversal ссылается на original movement, сериализует concurrent reversal и не позволяет повторно/некорректно обратить защищённую операцию.

Procurement final receipt имеет отдельную DB protection: его нельзя отменить generic warehouse reversal/correction.

## 10. History feed

Movement feed использует cursor/snapshot semantics, чтобы pagination не перескакивала при появлении новых journal rows.

Пользователь с `movement.read_own` видит разрешённый собственный scope. `movement.read_all` получает общий журнал и дополнительные filters.

## 11. Mutation safety

Catalog/warehouse mutations дополнительно требуют:

```text
REAL_INVENTORY_MUTATIONS_ENABLED=true
```

Default — false. При false API возвращает 423 для защищённых mutation paths.

## 12. Procurement integration

Final technical acceptance вызывает Warehouse service **до commit**, используя тот же SQLAlchemy session.

Создаваемое движение:

- type `RECEIPT`;
- line quantities из current procurement revision;
- deterministic procurement client request ID;
- destination из acceptance command.

Только после успешного warehouse write Procurement получает `COMPLETED` + `final_movement_id`.

## 13. Проверки

Критичные regression areas:

- concurrent/idempotent create;
- insufficient stock/custody;
- correction/reversal races;
- append-only DB triggers;
- projection drift;
- runtime projection DML denial;
- cursor/snapshot history;
- Procurement receipt protection;
- migration/readiness compatibility.
