# RBAC и Procurement — канонический контракт

Статус документа: APPROVED PRODUCT CONTRACT / RBAC FOUNDATION IMPLEMENTED / PROCUREMENT PENDING.

Дата фиксации: 2026-09-12.

Historical accepted production/runtime baseline перед началом feature cycle:

`1242f56c131d0f8c470e05cbaf209c48a37e85a4`

Этот документ является каноническим источником требований для текущего
RBAC + Procurement feature cycle.

RBAC foundation реализован и развёрнут в production с пятью ролями и
capability policy, описанными этим документом. Production и source используют
текущую five-role RBAC model. Procurement domain остаётся implementation
pending.

## 1. Основные принципы

- Backend является security boundary.
- Frontend только скрывает или показывает разрешённые действия.
- Роль пользователя хранится в PostgreSQL.
- Конкретные capabilities определяются server-side policy.
- В первой реализации не вводится динамический конструктор ролей.
- Роли являются фиксированными product roles.
- Access lifecycle `PENDING / APPROVED / REJECTED / BLOCKED` сохраняется
  независимо от role.
- Изменение role не должно менять user UUID, Telegram identity, warehouse
  history или custody history.
- Любое изменение role должно быть audit event.
- Procurement и Warehouse являются разными bounded domains.
- Procurement никогда не меняет остатки до отдельного подтверждения приёмки.
- Финальная приёмка закупки использует обычный immutable Warehouse movement.
- История закупки и её редакций не перезаписывается задним числом.

## 2. Роли

### ENGINEER — Инженер

Базовая рабочая роль.

Может:

- просматривать каталог;
- просматривать остатки;
- просматривать складские локации;
- выполнять обычные операционные движения склада;
- оформлять приход существующей номенклатуры;
- брать оборудование;
- возвращать оборудование;
- перемещать оборудование между локациями.

Не может:

- создавать новую номенклатурную карточку;
- редактировать карточку;
- архивировать карточку;
- удалять карточку;
- выполнять administrative correction/reversal/write-off;
- управлять пользователями;
- видеть или изменять procurement workflow.

Количество меняется только посредством Warehouse movement.
Прямого редактирования `stock quantity` нет.

### SENIOR_ENGINEER — Старший инженер

Получает все возможности ENGINEER.

Дополнительно может:

- создавать Item;
- редактировать Item;
- архивировать Item;
- удалить ошибочно созданный Item только если Item никогда не участвовал
  в movement/procurement и имеет zero stock;
- видеть общий movement journal;
- видеть procurement requests;
- выполнять техническую приёмку procurement;
- создавать отсутствующую catalog Item из proposed procurement line;
- фиксировать расхождение при приёмке.

Не может:

- создавать procurement request;
- выполнять закупку как Manager;
- назначать роли.

Если Item уже имеет warehouse/procurement history, hard delete запрещён.
Используется archive.

### MANAGER — Менеджер по закупкам

Может:

- просматривать каталог;
- просматривать фактические остатки;
- просматривать локации;
- видеть procurement requests;
- принимать procurement request в работу;
- вернуть request инициатору на корректировку;
- писать обязательный комментарий при возврате;
- предложить альтернативный состав закупки;
- выполнять действия по любой активной закупке;
- взять закупку на себя;
- передать ответственность другому MANAGER;
- передать поставку на техническую приёмку;
- видеть procurement history.

Не может:

- выполнять warehouse mutations;
- создавать или редактировать catalog Item;
- проводить техническую приёмку;
- изменять роли пользователей;
- создавать procurement request.

`assigned_manager_user_id` означает бизнес-ответственность, но не ACL.

Любой активный MANAGER может выполнить допустимое действие с активной
закупкой. Каждое действие фиксирует реального `actor_user_id`.

### ADMIN — Администратор

Получает административные складские и catalog capabilities.

Может:

- выполнять все обычные warehouse operations;
- выполнять write-off/correction/reversal;
- создавать/редактировать/архивировать catalog Item;
- управлять access lifecycle;
- назначать роли:
  - ENGINEER;
  - SENIOR_ENGINEER;
  - MANAGER;
- создавать procurement request;
- назначать ответственного Manager;
- просматривать весь procurement workflow;
- выполнять техническую приёмку procurement;
- фиксировать расхождения.

Не может:

- назначить ADMIN;
- назначить OWNER;
- изменить роль OWNER;
- заблокировать OWNER;
- штатно выполнять manager procurement workflow вместо MANAGER.

### OWNER — Владелец приложения

Специальная singleton role владельца приложения.

OWNER:

- имеет все warehouse/catalog/admin capabilities;
- может назначать ADMIN;
- может назначать ENGINEER / SENIOR_ENGINEER / MANAGER;
- может создавать procurement request;
- может просматривать и контролировать procurement;
- может проводить техническую приёмку;
- не является штатным исполнителем manager procurement workflow.

OWNER не назначается через обычный role-management API.

Configured recovery identity `ADMIN_TELEGRAM_USER_ID` является bootstrap /
recovery identity OWNER и не используется как implicit recipient рабочих
уведомлений. Operational notifications используют отдельный
`NOTIFICATION_TELEGRAM_USER_ID`.

Нельзя:

- понизить OWNER;
- заблокировать OWNER;
- удалить OWNER;
- назначить второго OWNER обычным UI/API.

Смена recovery OWNER допускается только guarded maintenance-only rotation:
атомарная передача OWNER между существующими Telegram identities под
PostgreSQL lock с immutable role/access audit. После commit конфигурационный
`ADMIN_TELEGRAM_USER_ID` меняется на нового OWNER до запуска runtime.

## 3. Capability model

Реализация должна проверять capabilities, а не размножать по application code
условия вида `role == ADMIN`.

Минимальные capability groups:

- `catalog.read`
- `catalog.manage`
- `catalog.archive`
- `catalog.delete_unused`
- `inventory.read`
- `inventory.operate`
- `inventory.admin`
- `movement.read_own`
- `movement.read_all`
- `procurement.read`
- `procurement.create`
- `procurement.manage`
- `procurement.accept`
- `access.manage_users`
- `access.assign_standard_roles`
- `access.assign_admin`

На первом этапе capability mapping является статическим backend policy,
а не отдельными database tables.

## 4. Migration contract существующих пользователей

При переходе со старой role model:

- `USER` -> `ENGINEER`;
- configured recovery identity -> `OWNER`;
- остальные `ADMIN` -> `ADMIN`.

Запрещено:

- пересоздавать User;
- менять User UUID;
- пересоздавать TelegramIdentity;
- терять AccessRequest history;
- терять UserAccessEvent history;
- терять custody;
- терять AuthSession history без отдельной причины.

Migration должна быть deterministic и downgrade-safe настолько, насколько это
возможно без потери новой role information.

## 5. Procurement domain

Procurement является отдельным backend module.

Не помещать procurement state в inventory/catalog models.

Основные сущности:

- ProcurementRequest;
- ProcurementRevision;
- ProcurementRevisionLine;
- ProcurementEvent;
- manager assignment;
- optional manager correction proposal;
- final Warehouse Movement linkage.

## 6. Procurement status lifecycle

UI-группа `Согласование` имеет два состояния:

### AGREEMENT_PENDING_MANAGER

Отображение:

`Ожидает менеджера`

Request создан ADMIN/OWNER и передан Manager.

### AGREEMENT_REVISION_REQUIRED

Отображение:

`Требует корректировки`

Manager вернул request инициатору.

Требуется обязательный комментарий.

Manager может приложить proposed alternative composition.

### PURCHASING

Отображение:

`В закупке`

Manager принял актуальную редакцию в работу.

### AWAITING_ACCEPTANCE

Отображение:

`На приёмке`

Manager сообщил, что ресурсы физически доступны и request передан техническим
сотрудникам.

На этом переходе stock НЕ меняется.

### COMPLETED

Отображение:

`Выполнена`

Ставится только после успешной технической приёмки и создания Warehouse
RECEIPT.

## 7. Procurement creation

Создать request могут:

- ADMIN;
- OWNER.

Request содержит:

- human-readable request number;
- initiator;
- assigned Manager;
- текущую immutable revision;
- список позиций;
- optional general comment;
- timestamps.

После отправки request Manager получает notification.

Других Managers каждой новой закупкой не спамим.

Они видят её в `Все активные`.

## 8. Procurement revision

После submission revision неизменяема.

Изменение состава создаёт новую revision.

Пример:

Revision 1:

- HDD A — 4;
- SSD B — 3;
- SSD C — 2.

Manager возвращает на корректировку:

`Бюджет позволяет оставить только два типа дисков.`

Manager может приложить alternative proposal:

- HDD A — 2;
- SSD B — 2.

Alternative proposal НЕ становится active revision автоматически.

Инициатор редактирует состав и отправляет Revision 2.

History сохраняет Revision 1, correction event и Revision 2.

## 9. Procurement lines

Line бывает двух типов.

### Existing catalog item

Хранит:

- `item_id`;
- immutable display snapshot;
- requested quantity.

### Proposed new item

Использует category schema аналогично форме `Добавить оборудование`.

Хранит snapshot:

- category;
- manufacturer/model;
- category-specific attributes;
- requested quantity.

Создание proposed line НЕ создаёт Item в catalog.

До финальной приёмки proposed line должна быть связана с реальным Item.

SENIOR_ENGINEER / ADMIN / OWNER получают действие:

`Создать карточку из позиции закупки`

Форма catalog Item предзаполняется snapshot из procurement line.

## 10. Multiple managers

У request один текущий assigned Manager.

Но любой активный MANAGER может выполнять manager actions с любой активной
закупкой.

Пример audit trail:

- Анна приняла request;
- Анна перевела в `В закупке`;
- Сергей сообщил `Ресурсы на месте`;
- assigned Manager при этом может остаться Анна.

Отдельные действия:

- `Взять на себя`;
- `Передать менеджеру`.

Изменение assignment является отдельным immutable event.

## 11. Correction loop

Manager может нажать:

`Вернуть на корректировку`

Обязателен comment.

Дополнительно разрешён structured alternative proposal.

Request -> `AGREEMENT_REVISION_REQUIRED`.

Инициатор создаёт новую revision и повторно отправляет Manager.

Цикл может повторяться несколько раз.

## 12. Передача на приёмку

Manager нажимает:

`Передать на приёмку`

Request -> `AWAITING_ACCEPTANCE`.

Stock не изменяется.

Notification получают:

- SENIOR_ENGINEER;
- ADMIN;
- OWNER.

## 13. Technical acceptance

Проводить acceptance могут:

- SENIOR_ENGINEER;
- ADMIN;
- OWNER.

Перед финальным подтверждением:

- все lines должны быть связаны с catalog Item;
- выбирается receiving StorageLocation;
- показывается полный состав;
- показывается количество каждой позиции.

Primary action:

`Подтвердить приёмку`

После первого нажатия обязательна confirmation dialog.

Пример:

`После подтверждения на склад будет добавлено:`

- Item A — 20 шт.;
- Item B — 15 шт.;
- Item C — 4 шт.

Final action:

`Подтвердить и оприходовать`

## 14. Atomic acceptance

Финальная acceptance должна быть atomic.

В одной PostgreSQL transaction:

1. lock ProcurementRequest;
2. повторно проверить status;
3. проверить current revision;
4. проверить catalog binding всех lines;
5. проверить receiving location;
6. создать обычный immutable Warehouse RECEIPT;
7. связать ProcurementRequest с Movement;
8. записать ProcurementEvent;
9. перевести request в COMPLETED;
10. enqueue notifications;
11. commit.

Если любой шаг падает — не меняется ни procurement, ни warehouse.

Повторный/double-click request не должен создать второй RECEIPT.

## 15. Расхождения

На `AWAITING_ACCEPTANCE` рядом с confirmation есть:

`Есть расхождения`

Comment обязателен.

Пример:

`Получено 19 из 20 модулей.`

При этом:

- stock не изменяется;
- RECEIPT не создаётся;
- request остаётся `AWAITING_ACCEPTANCE`;
- создаётся immutable discrepancy event;
- assigned Manager получает notification.

Автоматической частичной приёмки в первой версии нет.

Если требуется изменить официальный состав, это делается отдельным возвратом
в correction flow и новой revision, а не редактированием старой revision.

## 16. Warehouse linkage

Procurement quantity не является stock quantity.

`PURCHASING` и `AWAITING_ACCEPTANCE` никогда сами по себе не меняют склад.

Единственный stock-changing procurement transition:

`AWAITING_ACCEPTANCE -> COMPLETED`

через успешно созданный Warehouse RECEIPT.

Movement history должна показывать связь с procurement request.

Procurement history должна показывать созданный Movement.

## 17. Audit

Неизменяемо фиксируются:

- создание request;
- каждая revision;
- Manager acceptance;
- возврат на корректировку;
- comment;
- alternative proposal;
- изменение assigned Manager;
- `Взять на себя`;
- переход в `В закупке`;
- передача на приёмку;
- discrepancy;
- технический accepter;
- final Warehouse Movement;
- timestamps;
- actor каждого действия.

## 18. Concurrency

State transitions проверяются backend.

Использовать PostgreSQL row locking / deterministic conflict handling.

Если два Managers работают одновременно, устаревший несовместимый transition
должен получить conflict и перечитать актуальное состояние.

Нельзя полагаться только на disabled frontend button.

## 19. UI

Role-based navigation должна убирать недоступную функциональность, а не
показывать десятки disabled controls.

MANAGER:

- `Мои`;
- `Все активные`;
- `История`.

Procurement detail показывает:

- number/status;
- initiator;
- assigned Manager;
- active revision;
- positions;
- comments/events;
- revision history;
- разрешённые текущему actor actions.

SENIOR_ENGINEER видит procurement для monitor/acceptance, но не manager actions.

ENGINEER procurement section не видит.

## 20. Telegram notifications

Использовать существующий transactional notification/outbox подход.

Минимальные события:

- новая закупка -> assigned Manager;
- новая revision -> assigned Manager;
- возврат на корректировку -> initiator;
- передача на приёмку -> SENIOR_ENGINEER / ADMIN / OWNER;
- discrepancy -> assigned Manager;
- assignment transfer -> новый assigned Manager;
- completed -> initiator + Managers, участвовавшие в процессе, где это разумно.

Telegram message содержит краткий состав и deep link в Mini App.

Большой список сокращается, например первые 5 строк + количество оставшихся.

## 21. Email

Email является отдельным delivery phase после acceptance core workflow.

Целевой transport:

Microsoft Graph / OAuth.

Не использовать legacy Basic Auth SMTP как основной новый механизм.

Поддержать:

- To;
- CC;
- HTML/text body;
- procurement number;
- positions;
- deep/application link.

Email failure не должен откатывать procurement transaction.

Delivery должен идти асинхронно через outbox/worker semantics.

## 22. Что НЕ делать в первой реализации

Не добавлять без отдельного решения:

- partial warehouse acceptance;
- accounting/ERP;
- supplier directory;
- payment workflow;
- invoice OCR;
- attachment storage;
- price analytics;
- dynamic custom roles;
- external queue/Redis;
- automatic stock update по manager status;
- automatic creation Item из proposed line;
- silent rewrite procurement history.

## 23. Acceptance criteria RBAC

RBAC считается принятым только когда:

- migration старых roles прошла на PostgreSQL;
- recovery identity стал OWNER;
- остальные users получили корректные roles;
- backend permission matrix покрыта tests;
- ADMIN не может создать ADMIN/OWNER;
- OWNER может назначить ADMIN;
- OWNER нельзя заблокировать/понизить;
- role update audit сохраняется;
- role change применяется backend без нового login;
- role-specific frontend скрывает недоступные actions;
- старый warehouse behavior не регрессировал;
- full backend/frontend/CI gates зелёные.

## 24. Acceptance criteria Procurement

Procurement считается принятым только когда:

- revision history immutable;
- correction loop работает;
- Manager collaboration работает;
- assigned Manager не является ACL;
- proposed item не создаёт catalog Item автоматически;
- `Передать на приёмку` не меняет stock;
- discrepancy не меняет stock;
- final acceptance создаёт ровно один RECEIPT;
- double click/replay не создаёт duplicate receipt;
- procurement completion и Warehouse movement atomic;
- audit фиксирует фактического actor;
- Telegram notification flow покрыт tests;
- browser E2E покрывает основные role workflows;
- PostgreSQL integration покрывает state/concurrency invariants.
