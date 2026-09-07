# Architecture

## System

Spikatel Inventory — Telegram Mini App.

Основной путь:

Telegram → HTTPS / Cloudflare → nginx → FastAPI → PostgreSQL

Backend modules:

- auth / identity;
- access;
- catalog;
- inventory;
- notifications;
- telegram_bot;
- maintenance.

## Catalog

Каталог использует фиксированную hierarchy family → leaf.

Item является номенклатурной позицией.
Технические поля зависят от leaf category.
Search/facets выполняются backend и scoped текущим universe.

## Warehouse

Источник истины — immutable movement journal.

Current projection:

stock_balances(Item, Location, quantity)

Physical-unit/custody projection отсутствует.

Movement types:

- RECEIPT;
- ISSUE;
- RETURN;
- TRANSFER;
- WRITE_OFF;
- CORRECTION;
- REVERSAL.

MovementLine хранит Item snapshot и positive quantity.

## Transaction model

Создание movement выполняется одной PostgreSQL transaction:

1. normalize client_request_id;
2. advisory-lock idempotency key;
3. проверить replay/fingerprint;
4. lock original movement при необходимости;
5. lock locations;
6. lock Items;
7. lock/update StockBalance;
8. insert immutable Movement/MovementLine;
9. enqueue transactional outbox effects;
10. commit.

Negative balance запрещён.
Zero balance row удаляется.

## Idempotency

Scope:

actor_user_id + client_request_id

Replay одинакового payload возвращает существующий Movement.
Другой payload под тем же ключом возвращает conflict.

## Notifications

Telegram delivery использует PostgreSQL transactional outbox.

ISSUE notification создаётся до commit warehouse transaction.

Outbox имеет deterministic dedupe key.
Delivery worker выполняет retry/DEAD lifecycle независимо от warehouse request.

TELEGRAM_DELIVERY_GUARANTEE=AT_LEAST_ONCE_NOT_EXACTLY_ONCE

### Duplicate delivery window

Transactional outbox гарантирует сохранность notification intent, но внешний
Telegram Bot API не предоставляет системе атомарный commit вместе с локальным
delivery-state update. Если Telegram принял сообщение, а worker завершился до
фиксации успешной доставки в PostgreSQL, notification может быть отправлена повторно
после retry.

Поэтому delivery semantics — at-least-once, а не exactly-once. Dedupe key
защищает от повторного создания одного и того же outbox intent внутри системы,
но не превращает внешний Bot API delivery в exactly-once transport.

## Runtime provenance

Application image фиксирует source revision в OCI metadata:

`org.opencontainers.image.revision`

Git checkout на production VM и revision реально запущенного container image
являются разными operational facts. Runtime provenance проверяется по metadata
образа, а не выводится только из состояния checkout.

## Authorization

Approved USER:

- catalog;
- stock;
- own actor movement history;
- ISSUE;
- RETURN.

ADMIN дополнительно:

- общий journal;
- employee filter;
- Item/Location administration;
- RECEIPT;
- TRANSFER;
- WRITE_OFF;
- CORRECTION/REVERSAL.

Frontend authorization не является security boundary.

## Safety gate

Real inventory mutations защищены REAL_INVENTORY_MUTATIONS_ENABLED.

## Reconciliation

Projection consistency проверяется:

backend/scripts/reconcile_inventory_projections.sql

Zero returned rows означает, что stock projection совпадает с journal.

## Bootstrap

Workbook importer предназначен только для initial quantity bootstrap.

Он поддерживает:

- dry-run;
- transactional import;
- explicit destination location;
- double-import protection.

Реальный authoritative workbook находится вне repository.
