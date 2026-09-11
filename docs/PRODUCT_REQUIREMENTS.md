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
5. Сколько оборудования сейчас числится в custody каждого USER?

Персональная ответственность ведётся агрегированно как User × Item × quantity.
Это не serial/current-holder модель физических экземпляров и пока не требует
отдельного пользовательского экрана «Моё оборудование».

Regular production warehouse mutations дополнительно защищены
`REAL_INVENTORY_MUTATIONS_ENABLED`. Initial one-shot bootstrap и normal
operational mutations являются разными safety boundaries.

## Current feature-cycle requirements — RBAC / Procurement

Accepted production baseline перед feature cycle:

`1242f56c131d0f8c470e05cbaf209c48a37e85a4`

Текущая двухролевая реализация USER/ADMIN мигрирует на:

ENGINEER / SENIOR_ENGINEER / MANAGER / ADMIN / OWNER.

Canonical role matrix, procurement lifecycle, immutable revision rules,
manager collaboration, discrepancy handling и atomic warehouse acceptance:

`docs/RBAC_PROCUREMENT.md`

Для текущего feature cycle этот документ имеет приоритет над историческими
USER/ADMIN role labels ниже до завершения их migration.

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

USER ISSUE увеличивает его `UserItemCustodyBalance`.

USER RETURN уменьшает его `UserItemCustodyBalance` и не может превысить
фактическое количество, числящееся за пользователем.

ADMIN ISSUE/RETURN не создают персональную custody.

APPROVED USER нельзя перевести в BLOCKED, пока за ним числится оборудование.

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

USER видит только движения, где он actor.
ADMIN видит общий journal и может фильтровать по employee.

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

USER:

- Взять;
- Вернуть.

ADMIN дополнительно:

- Переместить;
- Приход;
- Списать.

## Архивирование

Archived Item запрещает новый RECEIPT и ISSUE.

RETURN, TRANSFER, WRITE_OFF, CORRECTION и REVERSAL остаются допустимыми для
завершения существующего складского состояния.

Location с остатком архивировать нельзя.

## Telegram

ADMIN получает Telegram notification на каждый новый ISSUE.

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
