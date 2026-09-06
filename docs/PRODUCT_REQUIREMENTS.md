# Product Requirements — Spikatel Inventory

## Назначение

Spikatel Inventory — внутреннее Telegram Mini App для складского учёта
оборудования и расходных материалов ЦОД.

Система должна достоверно отвечать:

1. что есть в наличии;
2. где это находится;
3. у кого это находится;
4. кто и когда оформил изменение;
5. откуда и куда физически переместилось оборудование.

PostgreSQL — канонический источник данных.

В production приняты Stages 4–8B и post-8B Telegram/catalog UX.
Migration head — `a2b3c4d5e6f7`. Stage15A automated off-VM backup и Stage15B
real isolated restore — `PASS`; Stage15 technical hardening завершён. Production-data gate намеренно остаётся закрытым до следующего roadmap.
AUD-01 fail-closed mutation gate принят в production.

## Пользователи и роли

Базовые роли:

- `ADMIN`;
- `USER`.

Backend, а не frontend, является authorization boundary.

`ADMIN` выполняет administrative/catalog/warehouse mutations только когда
deployment safety policy разрешает mutations.

Production до отдельного operator decision работает с
`REAL_INVENTORY_MUTATIONS_ENABLED=false`; authorization и deployment safety
gate являются независимыми boundaries.

`USER` после `APPROVED` работает только в разрешённых пользовательских
сценариях. Полный self-service warehouse UI относится к следующим roadmap
stages.

## Telegram identity и access

Telegram — внешний identity provider.

Внутренняя identity пользователя — UUID `User.id`.
Telegram username не используется как постоянный идентификатор.

Первый ADMIN задаётся явным `ADMIN_TELEGRAM_USER_ID`.

Access lifecycle:

- `PENDING`;
- `APPROVED`;
- `REJECTED`;
- `BLOCKED`.

`REJECTED` допускает повторный запрос.
`BLOCKED` запрещает новый запрос.

ADMIN получает approve/reject notification в Telegram.

Если ADMIN notification после retries стала `DEAD`, повторный explicit access
request:

- не создаёт второй `AccessRequest`;
- не создаёт вторую callback pair;
- переиспользует существующую callback pair;
- возвращает соответствующую terminal outbox delivery в `PENDING`.

## Каталог

`Item` — каталожная позиция, не физическая serial unit.

Базовые категории:

- SFP / optical transceivers;
- optical cabling;
- copper network cabling;
- power cables;
- network interface cards;
- disks/drives.

Category schemas metadata-driven и version-controlled через Alembic.

Reference spreadsheets используются для catalog design и терминологии, но не
являются inventory database/import source.

## Режимы учёта

### QUANTITY

Для однородных позиций.

Current position:

- Location;
- либо holder User.

Количество — положительное целое.
Отрицательные остатки запрещены.

### SERIAL

Для индивидуально отслеживаемых физических единиц.

Stage 6 unit содержит:

- serial number;
- optional WWN;
- optional physical-unit comment;
- current state;
- current Location либо holder;
- timestamps.

`asset_tag`, firmware и другие расширенные physical-unit metadata не входят в
Stage 6.

## Warehouse operations

Канонические операции:

- `RECEIPT`;
- `ISSUE`;
- `RETURN`;
- `TRANSFER`;
- `WRITE_OFF`;
- `CORRECTION`;
- `REVERSAL`.

Любое изменение stock/custody происходит только через Movement.

`Movement` и `MovementLine` — append-only canonical history.

Ошибочная операция не переписывается задним числом.
Используется linked correction либо reversal.

## Actor и physical holder

Система различает:

- actor — кто оформил действие;
- source/destination holder — у кого оборудование находилось физически.

История сохраняет display snapshots значимых изменяемых данных.

## Concurrency и idempotency

Movement mutation требует `client_request_id`.

Повтор того же `(actor, client_request_id)` и payload возвращает исходный
movement.

Тот же key с другим payload — conflict.

При concurrent выдаче последней quantity/serial unit успешно завершиться может
только одна операция.

## Location lifecycle

Location — first-class физическая точка хранения.

Lifecycle:

- `ACTIVE`;
- `ARCHIVED`.

Локацию с current inventory нельзя архивировать.

Movement не может создать current inventory в archived destination.

## Archived Item policy

Archive Item не удаляет существующий stock.

Для archived Item:

- новый receipt запрещён;
- новый issue запрещён;
- return/transfer/write-off existing inventory разрешены;
- допустимый reversal разрешён;
- correction не должна создавать новый external archived inventory.

## Telegram delivery

Application transaction не вызывает Telegram Bot API напрямую.

Маршрут:

    PostgreSQL transaction
      -> NotificationOutbox
      -> telegram-worker
      -> Cloudflare Telegram Gateway
      -> Telegram Bot API

Production gateway URL обязан использовать HTTPS.

Для Bot API Cloudflare Worker хранит Telegram bot token как secret
`BOT_TOKEN`. Тот же credential независимо доступен backend как
`TELEGRAM_BOT_TOKEN` только для server-side HMAC-проверки Mini App `initData`;
`telegram-worker` bot token не получает.

## Frontend

Текущий frontend сохраняет runtime/auth/access boundary и реализует рабочий
catalog UX:

- единый application shell и Telegram-aware navigation;
- API-driven catalog categories;
- global/category debounced search; backend serial/WWN search соблюдает
  privacy scope: `ADMIN` ищет по всем physical units, обычный `USER` — только
  по текущим `ISSUED` units, которые числятся за ним;
- metadata/facet-driven exact, boolean и range filters;
- bounded high-cardinality facet values с lazy загрузкой и явной дозагрузкой
  следующих страниц без потери уже выбранных значений;
- sorting и progressive pagination;
- compact item cards и Item detail;
- role-aware metadata-driven Admin create/edit/archive, inline Manufacturer и
  backend duplicate-check UX;
- Item detail stock-by-location и custody/holder projections;
- self-view «Моё» для QUANTITY и SERIAL по внутреннему `User.id`;
- URL-owned search/filter/sort navigation state;
- loading/error/empty/retry states.

Telegram SDK поставляется same-origin:

    /vendor/telegram/telegram-web-app.js

CI проверяет SHA-256 vendored SDK.

Frontend отдельно обрабатывает SDK load error и timeout. Backend остаётся
authorization boundary. Stage 8 viewport acceptance выполняется Playwright на
Telegram Desktop narrow, Android-like, iPhone-like и desktop profiles.
Warehouse mutations/history относятся к следующим stages.

## Technical retention

Technical retention не затрагивает warehouse journal.

Bounded cleanup применяется только к:

- expired/revoked auth sessions;
- processed Telegram updates;
- terminal notification outbox;
- callbacks terminal access decisions.

## Production-data gate

Stage15A backup и Stage15B isolated restore уже приняты.

Production-data gate остаётся закрыт до полного Stage15C acceptance, включая:

1. fail-closed server-side mutation gate;
2. unambiguous checkout/runtime backup provenance;
3. exact S3 lifecycle-prefix validation;
4. durable application rollback artifact;
5. controlled backup failure drill;
6. command-level recovery rehearsal;
7. stale inventory-source assumptions retired; real-data source remains undefined;
8. final CI/security/runtime/host acceptance;
9. zero-drift production reconciliation;
10. canonical documentation closure.

Даже после policy-разрешения real inventory остаётся отдельным explicit
operator action.

## Deferred

В текущую Stage 8 не входят:

- frontend warehouse operations;
- stocktake;
- procurement/reservations;
- opening balance / Excel inventory import;
- media;
- QR/barcode;
- NetBox integration;
- asset tag / firmware metadata;
- microservices/CQRS/event-sourcing framework.

Дальнейший порядок работ определяет `docs/ROADMAP.md`.
