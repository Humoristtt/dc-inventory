# Требования Spikatel Inventory

Warehouse Domain V2 развёрнут и принят в production. Telegram Mini App отвечает на вопросы: какая номенклатура есть, сколько её на локациях, какие immutable движения изменили остатки, кто был actor и какое количество числится за custody-capable сотрудниками.

**Контуры не смешиваются:** последний зафиксированный production Procurement Alembic head `c3d4e5f6a7b8`; текущий source head `a9c0d1e2f3a4` и CP-07–12 локально проверены, но не подтверждены на production. Regular mutations закрыты отдельным gate `REAL_INVENTORY_MUTATIONS_ENABLED=false`; initial bootstrap уже состоялся через guarded one-shot path.

## Склад и ответственность

`Item` — номенклатура, не физический экземпляр. `StockBalance = Item × StorageLocation × positive quantity`; `UserItemCustodyBalance = User × Item × positive quantity`. ENGINEER/SENIOR_ENGINEER ISSUE увеличивает их custody, RETURN уменьшает её и не может превышать имеющееся количество. ADMIN/OWNER складские движения не создают personal custody автоматически. Пользователя с ненулевой custody нельзя заблокировать или перевести в роль, не поддерживающую custody. Доступ и custody-changing movements синхронизируются по PostgreSQL lock.

Система **не** ведёт serial/WWN/current-holder конкретного physical unit. Отдельного экрана «Моё оборудование» нет; custody является backend integrity projection. Количества изменяются только движениями, а не редактированием карточки Item.

## Роли и безопасность

Production и source используют `ENGINEER / SENIOR_ENGINEER / MANAGER / ADMIN / OWNER` с backend-derived capabilities. OWNER singleton/recovery role; ADMIN не назначает ADMIN/OWNER. MANAGER имеет read-only catalog/stock, manager procurement actions, но не Warehouse mutations или общий movement journal. SENIOR_ENGINEER видит общий journal, управляет каталогом и проводит technical procurement acceptance. ADMIN/OWNER администрируют склад, пользователей и техническую приёмку. Frontend скрывает недоступные действия, но не является security boundary. Canonical matrix и state machine — `docs/RBAC_PROCUREMENT.md`.

Auth: Telegram initData HMAC на backend, server-side HttpOnly session, независимый access lifecycle PENDING/APPROVED/REJECTED/BLOCKED. Owner rotation — только guarded CLI, не обычный UI/API. Настоящие credentials, datasets, private IDs и workbook contents в public repository запрещены.

## Каталог

Фиксированная family → leaf hierarchy: трансиверы Ethernet/FC; оптические патч-корды и сплиттеры; сетевые адаптеры Ethernet/FC; SSD/HDD; RAM; PCIe; кабели питания. Item создаётся только в leaf. Machine key отделён от русского display name. «Дальние» — derived scope с нормализованной reach_m ≥ 2000, не category; неоднозначные значения — явная ошибка/validation warning, без догадки.

Backend отдаёт scoped dynamic facets внутри выбранной category/search; single-value dimensions скрыты. Color оптического патч-корда optional free text, distinct suggestions, участвует в identity только при заполнении. Item detail показывает attributes, total stock и breakdown по StorageLocation. Архивирование Item запрещает новый RECEIPT/ISSUE, но разрешает допустимое завершение существующего остатка через RETURN/TRANSFER/WRITE_OFF/CORRECTION/REVERSAL. Локацию с остатком архивировать нельзя. Спецификация полей — `docs/CATALOG_SCHEMA.md`.

## Warehouse movements

RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION, REVERSAL хранятся в immutable journal. Actor и custody различаются. Idempotent replay одного actor/request/payload возвращает существующее движение, несовпадающий payload — conflict. Negative stock/custody запрещены, zero projection rows не хранятся. Проекции stock/custody сверяются read-only reconciliation по journal; normal result — zero rows.

ENGINEER видит собственную actor-history; SENIOR_ENGINEER/ADMIN/OWNER — общий журнал и employee filter; MANAGER не видит journal. Периоды: 7 дней, 30 дней, 3 месяца (по умолчанию), год, всё время. Фильтры: type, hierarchy/category, location. ENGINEER/SENIOR_ENGINEER выполняют «Взять», «Вернуть», «Переместить», «Приход»; ADMIN/OWNER дополнительно — write-off, correction, reversal.

## Procurement

Закупка создаётся ADMIN/OWNER и использует immutable revisions, events и назначенного Manager как ответственность, не ACL. Любой активный MANAGER может работать с любой активной закупкой, но actor фиксируется в event. Состояния: «Ожидает менеджера», «Требует корректировки», «В закупке», «На приёмке», «Выполнена». Корректировка создаёт новую revision, альтернативное предложение не применяет её автоматически. Proposed line до приёмки не создаёт Item. Manager transfer to acceptance и discrepancy не меняют stock.

Техническая приёмка SENIOR_ENGINEER/ADMIN/OWNER с двойным подтверждением и проверкой всех Item bindings/location атомарно создаёт ровно один Warehouse RECEIPT и переводит закупку в COMPLETED. Generic CORRECTION/REVERSAL этого final RECEIPT запрещены. Partial acceptance не входит в первый release. Production real Telegram Procurement acceptance ещё не подтверждена.

## Уведомления и optional email

ISSUE ставит deduplicated Telegram intent в одной транзакции с warehouse movement. Procurement notifications также используют transactional outbox. Внешняя доставка Telegram и Microsoft Graph email — at-least-once, не exactly-once: возможен duplicate side effect при потерянном подтверждении. Email реализован в source, но production по умолчанию выключен `EMAIL_DELIVERY_ENABLED=false`; для enablement нужны отдельные secrets, Compose profile и live acceptance.

## Initial bootstrap

Initial production inventory bootstrap — guarded one-shot operator operation. Она валидирует внешний workbook, ожидаемые counts/quantity и SHA, требует закрытый mutation gate и empty warehouse domain, проверяет existing APPROVED ADMIN, атомарно создаёт target StorageLocation и opening RECEIPT, выполняет post-write counts и zero-drift reconciliation до commit. Validation-only workbook reader не изменяет БД. Локальный `--import-local` helper допускается только на disposable loopback test DB с существующей active Location; он не заменяет production bootstrap.

Bootstrap уже принят с post-import verified off-VM backup и Telegram visual acceptance. Повторный запуск на наполненной production DB запрещён.
