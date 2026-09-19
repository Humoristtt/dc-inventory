# RBAC и Procurement — канонический контракт

Статус на 19.09.2026: RBAC foundation и Procurement domain развёрнуты в production по последней документированной проверке (Alembic `c3d4e5f6a7b8`). Production и source используют пять ролей и backend capability policy. Procurement domain также содержит локальную audit remediation до source Alembic `a9c0d1e2f3a4`; эти изменения **не** считаются production state до отдельного cutover и runtime-provenance acceptance. Real Telegram Procurement acceptance текущего нового release не зафиксирован. Regular warehouse gate — `REAL_INVENTORY_MUTATIONS_ENABLED=false`.

Historical feature-cycle baseline: `1242f56c131d0f8c470e05cbaf209c48a37e85a4`. Дальнейшие подтверждённые изменения и неисполненные проверки отражены в `docs/AUDIT_0_12_REMEDIATION.md` и `docs/HISTORY.md`.

## 1. Предметные границы

Backend — единственная authorization boundary. Frontend только скрывает/показывает действия; User role сохраняется в PostgreSQL, capabilities вычисляются статической server-side policy, динамических ролей пока нет. Access lifecycle `PENDING / APPROVED / REJECTED / BLOCKED` независим от роли. Изменение роли сохраняет User UUID, TelegramIdentity, warehouse/custody/access history и записывает неизменяемый `UserRoleEvent`. Procurement и Warehouse — отдельные модули. Статус закупки не меняет остатки до атомарной финальной приёмки.

`ProcurementRequest.final_movement_id` ссылается на защищённый финальный RECEIPT. Generic Warehouse CORRECTION/REVERSAL этого движения запрещены application service и PostgreSQL invariant. Отмена completed procurement потребует отдельного бизнес-процесса.

## 2. Роли и capability matrix

| Роль | Разрешено | Не разрешено |
|---|---|---|
| ENGINEER | Каталог/остатки/локации; своя actor-history; ISSUE, RETURN, RECEIPT существующей позиции, TRANSFER | Управление каталогом, admin adjustments, роли, закупки |
| SENIOR_ENGINEER | ENGINEER + catalog create/edit/archive, общий journal, просмотр закупок и technical acceptance, proposed Item binding | Создать procurement request, manager workflow, role assignment, `inventory.admin` |
| MANAGER | Каталог/остатки read-only, все активные закупки, manager actions и history | Warehouse mutations, каталог manage, техническая приёмка, назначение ролей, создание закупки |
| ADMIN | Каталог/warehouse administration, write-off/correction/reversal, access lifecycle, стандартные роли, закупка create/monitor, technical acceptance | Назначить ADMIN/OWNER, изменить/заблокировать OWNER, штатно исполнять manager workflow |
| OWNER | ADMIN + назначение ADMIN; единственная recovery identity; procurement create/monitor/acceptance | Обычное назначение второго OWNER, собственная блокировка/понижение через normal API |

ENGINEER/SENIOR_ENGINEER ISSUE/RETURN изменяют только допустимую custody собственных users. ADMIN/OWNER движения склада не создают персональную custody автоматически. Пользователя с ненулевой custody нельзя заблокировать или перевести на роль без custody. Все проверки на backend, с PostgreSQL lock при concurrent access/movement.

Capabilities: `catalog.read`, `catalog.manage`, `catalog.archive`, `catalog.delete_unused`, `inventory.read`, `inventory.operate`, `inventory.admin`, `movement.read_own`, `movement.read_all`, `procurement.read`, `procurement.create`, `procurement.manage`, `procurement.accept`, `access.manage_users`, `access.assign_standard_roles`, `access.assign_admin`. MANAGER не моделируется как линейный `role >= ...`.

## 3. OWNER и migration существующих пользователей

Историческая RBAC migration `a1b2c3d4e5f6`: `USER` → `ENGINEER`, configured recovery identity → `OWNER`, остальные ADMIN сохраняют ADMIN. Не пересоздаются User/TelegramIdentity и не удаляется audit/custody/session history. Migration несовместима со старым runtime; historical maintenance cutover выполнен. Downgrade fail-closed, если есть новые роли/role events, которые старая двухролевая модель не представляет.

`ADMIN_TELEGRAM_USER_ID` — bootstrap/recovery OWNER, но **не** implicit адресат рабочих уведомлений. `NOTIFICATION_TELEGRAM_USER_ID` — отдельный recipient. OWNER singleton и не назначается нормальным API. Смена OWNER — только guarded maintenance CLI `python -m app.bootstrap.recovery_owner_rotation`: существующая Telegram identity, нет custody у target, verified backup, остановленный runtime, одна PostgreSQL transaction с locks и immutable role/access audit, отзыв sessions обоих users. После COMMIT сначала изменить `ADMIN_TELEGRAM_USER_ID` на нового OWNER, затем запускать backend; иначе recovery reconciliation fail-closed. Полная операторская процедура — `docs/DEPLOYMENT.md`.

## 4. Procurement persistence и бизнес-правила

Модуль `procurement` отделён от `catalog`/`inventory`. Сущности: `ProcurementRequest`, immutable `ProcurementRevision` и lines, immutable `ProcurementEvent`, manager assignment/alternative proposal и final Warehouse Movement linkage. Assigned Manager означает ответственность, **не ACL**: любой APPROVED MANAGER может работать с любой активной закупкой; каждый event фиксирует фактического actor.

Закупка создаётся ADMIN/OWNER, содержит number/initiator/assigned manager, активную immutable revision, позиции, комментарий и timestamps. Новая закупка уведомляет назначенного Manager; остальных Managers не спамит и остаётся видимой во «Все активные». Actions «Взять на себя» / «Передать менеджеру» записывают immutable assignment events.

После submission нельзя менять старую revision — корректировка создаёт новую, сохраняя предыдущие позиции, комментарии и alternative proposal. Manager alternative composition не становится active revision автоматически. Позиция бывает существующей (`item_id` + display snapshot) либо предлагаемой (category, manufacturer/model, typed attributes, quantity snapshot). Proposed line не создаёт catalog Item автоматически. Перед final acceptance SENIOR_ENGINEER/ADMIN/OWNER должен связать все proposed lines с реальными Items, при необходимости через prefilled форму «Создать карточку из позиции закупки».

## 5. State machine

| Состояние | UI | Смысл |
|---|---|---|
| `AGREEMENT_PENDING_MANAGER` | Ожидает менеджера | Передана Manager, stock не меняется |
| `AGREEMENT_REVISION_REQUIRED` | Требует корректировки | Manager вернул инициатору, обязательный комментарий, optional structured alternative |
| `PURCHASING` | В закупке | Менеджер принял текущую редакцию |
| `AWAITING_ACCEPTANCE` | На приёмке | Ресурсы переданы на техническую приёмку, stock ещё не меняется |
| `COMPLETED` | Выполнена | Техническая приёмка завершена и создан ровно один RECEIPT |

Manager correction loop может повторяться. Передача на приёмку уведомляет технические роли, но не меняет stock. Кнопка «Есть расхождения» требует comment, создаёт immutable discrepancy event, уведомляет assigned Manager, сохраняет `AWAITING_ACCEPTANCE` и не создаёт RECEIPT. Partial acceptance в первой версии отсутствует; изменение официального состава идёт через correction + новую revision.

## 6. Техническая приёмка и атомарность

Только SENIOR_ENGINEER/ADMIN/OWNER. Перед подтверждением все lines связаны с Items, выбрана receiving StorageLocation, показан состав/количества. UI требует двух действий: «Подтвердить приёмку» и финальное «Подтвердить и оприходовать» с confirmation dialog.

В одной PostgreSQL transaction: lock request → перепроверить status/current revision → validate item bindings/location → создать immutable Warehouse RECEIPT → связать `final_movement_id` → записать event → перевести в `COMPLETED` → enqueue notifications → COMMIT. Любой сбой откатывает Procurement и Warehouse одновременно. Concurrent несовместимые manager transitions возвращают conflict; double click/idempotent replay не создаёт второй RECEIPT.

`PURCHASING` и `AWAITING_ACCEPTANCE` сами по себе не меняют stock. Procurement quantity не является stock quantity. Movement history и procurement history сохраняют двустороннюю связь. Final RECEIPT нельзя обходить generic stock adjustments.

## 7. UI и notifications

ENGINEER не видит раздел закупок. MANAGER видит «Мои», «Все активные», «История»; SENIOR_ENGINEER — monitor/acceptance без manager actions. Detail: номер, status, initiator, assigned manager, active revision, lines, comments/events, revision history, разрешённые действия. Disabled frontend button никогда не заменяет backend authorization.

Telegram events: новая закупка/новая revision → assigned Manager; возврат на корректировку → initiator; передача на приёмку → технические роли; discrepancy → assigned Manager; assignment transfer → новый Manager; completion → initiator и участвовавшие Managers по текущему уведомительному контракту. Notification содержит краткий состав и Mini App deep link; большой список сокращается. `NotificationOutbox` фиксирует intent транзакционно; доставка через Gateway at-least-once, duplicate внешнего сообщения возможен.

## 8. Optional email

В source реализованы Microsoft Graph OAuth application client, To/CC, HTML/text body, procurement number/positions/deep link, durable email outbox, retry/DEAD и отдельная least-privilege identity. Email failure не откатывает procurement transaction; отправка доступна только после `COMPLETED`. Production email по умолчанию выключен (`EMAIL_DELIVERY_ENABLED=false`), включение требует явных secrets/profile `email`/live acceptance. Потерянное подтверждение Graph может привести к повторной отправке — exactly-once не заявляется. SMTP Basic Auth не используется как целевой транспорт.

## 9. Acceptance и исключённый scope

RBAC acceptance требует PostgreSQL migration и OWNER invariant, audit events, permission matrix, текущую backend authorisation, role-specific frontend, tests и CI. Procurement acceptance требует immutable revisions/events, correction loop, multi-manager workflow, discrepancy без stock changes, unique final RECEIPT, concurrency/idempotency, PostgreSQL integration, browser E2E, Telegram acceptance и production provenance. Source unit/integration PASS не означает real Telegram acceptance нового production release.

Без отдельного решения не добавлять partial acceptance, ERP/accounting, supplier directory, payments, invoice OCR, attachments, price analytics, dynamic roles, Redis/external queues или автоматический stock update по manager status.
