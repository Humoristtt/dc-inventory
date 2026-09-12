# Product Requirements — Spikatel Inventory

## Цель

Telegram Mini App для складского учёта оборудования ЦОД.

Warehouse Domain V2 развёрнут и принят в production.
Initial production inventory bootstrap выполнен и подтверждён
post-import reconciliation + verified backup + Telegram visual acceptance.

Система отвечает на вопросы:

1. Что есть в каталоге?
2. Сколько оборудования есть сейчас?
3. На каких складских локациях оно находится?
4. Кто и когда выполнил приход, выдачу, возврат, перемещение или списание?
5. Сколько оборудования сейчас числится в custody каждого custody-capable сотрудника?

Персональная ответственность ведётся агрегированно как User × Item × quantity.
Это не serial/current-holder модель физических экземпляров и пока не требует
отдельного пользовательского экрана «Моё оборудование».

Regular production warehouse mutations дополнительно защищены
`REAL_INVENTORY_MUTATIONS_ENABLED`. Initial one-shot bootstrap и normal
operational mutations являются разными safety boundaries.

## Current feature-cycle requirements — RBAC / Procurement

Accepted production baseline перед feature cycle:

`1242f56c131d0f8c470e05cbaf209c48a37e85a4`

Source RBAC foundation уже реализует:

ENGINEER / SENIOR_ENGINEER / MANAGER / ADMIN / OWNER.

Accepted production baseline остаётся на historical USER / ADMIN до отдельного
maintenance cutover `f8a9b0c1d2e3 -> a1b2c3d4e5f6`.

Canonical role matrix, procurement lifecycle, immutable revision rules,
manager collaboration, discrepancy handling и atomic warehouse acceptance:

`docs/RBAC_PROCUREMENT.md`

Для текущего feature cycle каноническая role/capability matrix находится в
`docs/RBAC_PROCUREMENT.md`. Historical USER / ADMIN terminology относится только
к ещё не обновлённому accepted production baseline, а не к source RBAC model.

## Каталог

Фиксированная иерархия:

- Трансиверы
  - Ethernet
  - Fibre Channel
- Оптика
  - Оптические патч-корды
  - Сплиттеры и делители
- Сетевые адаптеры
  - Ethernet
  - Fibre Channel
- Накопители
  - SSD
  - HDD
- Оперативная память
- PCIe-адаптеры
- Кабели питания

Item создаётся только в leaf category.

Machine key категории отделён от русского display name.

Дальние — derived view, а не категория.
Базовое правило: reach_m >= 2000.

Неоднозначная дальность должна приводить к явной ошибке/import warning, а не к
догадке.

## Поиск и фильтры

Backend возвращает dynamic scoped facets.

Facet строится внутри текущего universe выбранной category/search.
Dimension с единственным distinct value скрывается.

Цвет оптического патч-корда:

- optional free text;
- suggestions берутся из существующих distinct values;
- если указан, участвует в identity;
- пустое значение не отображается.

## Остатки

Текущий остаток:

Item × StorageLocation → quantity

Item detail показывает:

- технические характеристики;
- общий остаток;
- breakdown по локациям.

## Custody

ENGINEER / SENIOR_ENGINEER ISSUE увеличивает их
`UserItemCustodyBalance`.

ENGINEER / SENIOR_ENGINEER RETURN уменьшает `UserItemCustodyBalance` и не
может превысить фактическое количество, числящееся за пользователем.

ADMIN / OWNER ISSUE/RETURN не создают персональную custody.

APPROVED пользователя с ненулевой custody нельзя перевести в BLOCKED или в
роль, которая не поддерживает custody.

Custody projection должна транзакционно согласовываться с immutable movement
journal и участвует в canonical reconciliation.

## Движения

Типы:

- RECEIPT;
- ISSUE;
- RETURN;
- TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

Journal immutable.

ENGINEER видит только движения, где он actor.
SENIOR_ENGINEER / ADMIN / OWNER видят общий journal и могут фильтровать по
employee.
MANAGER movement journal не видит.

Периоды:

- 7 дней;
- 30 дней;
- 3 месяца — default;
- год;
- всё время.

Дополнительные фильтры:

- movement type;
- hierarchy/category;
- location.

## UI операций

ENGINEER / SENIOR_ENGINEER:

- Взять;
- Вернуть;
- Переместить;
- Приход существующей номенклатуры.

ADMIN / OWNER дополнительно:

- Списать;
- administrative correction;
- reversal.

MANAGER warehouse mutations не выполняет.

## Архивирование

Archived Item запрещает новый RECEIPT и ISSUE.

RETURN, TRANSFER, WRITE_OFF, CORRECTION и REVERSAL остаются допустимыми для
завершения существующего складского состояния.

Location с остатком архивировать нельзя.

## Telegram

Текущий configured notification recipient получает Telegram notification на каждый новый ISSUE.

Movement и notification outbox record фиксируются одной транзакцией.

## Безопасность

Сохраняется текущая access/auth модель:

- ADMIN;
- USER;
- PENDING / APPROVED / REJECTED / BLOCKED;
- server-side Telegram initData verification;
- HttpOnly session;
- REAL_INVENTORY_MUTATIONS_ENABLED mutation gate.

## Initial bootstrap

Initial production inventory bootstrap является guarded one-shot operation.

Production bootstrap:

- сначала выполняет read-only validation внешнего workbook;
- проверяет expected workbook rows/items/quantity и source SHA contract;
- требует закрытый regular mutation gate;
- требует пустой warehouse domain;
- атомарно создаёт target StorageLocation;
- создаёт quantity-only catalog/stock state;
- создаёт одну opening RECEIPT transaction;
- выполняет post-write count/quantity checks;
- требует zero-drift projection reconciliation до commit;
- fail-closed запрещает повторный bootstrap после первого успешного load.

Validation-only запуск workbook reader не изменяет БД.

Локальный `--import-local` helper предназначен только для disposable loopback
test database и использует заранее существующую active Location; это не
production bootstrap path.

Authoritative workbook хранится вне public repository.
