# Product Requirements — Spikatel Inventory

## Цель

Telegram Mini App для складского учёта оборудования ЦОД.

Stage15 technical hardening завершён. Warehouse Domain V2 этой feature-ветки
является следующим schema/product состоянием и требует отдельного merge/deploy
acceptance перед production rollout.

Система должна отвечать на вопросы:

1. Что есть в каталоге?
2. Сколько оборудования есть сейчас?
3. На каких складских локациях оно находится?
4. Кто и когда выполнил приход, выдачу, возврат, перемещение или списание?

Персональный баланс оборудования сотрудников не ведётся.

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

Начальный workbook импортируется только в явно существующую StorageLocation.

Импорт:

- quantity-only;
- транзакционный;
- создаёт opening RECEIPT;
- защищён от повторного bootstrap;
- dry-run не изменяет БД.

Authoritative workbook хранится вне public repository.
