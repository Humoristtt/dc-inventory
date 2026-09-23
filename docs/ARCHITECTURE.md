# Архитектура Spikatel Inventory

Система — модульный монолит: один FastAPI backend обслуживает Telegram Mini App, каталог, склад, пользователей и закупки; PostgreSQL хранит предметные данные и транзакционный журнал. Отдельные процессы выполняют отправку уведомлений и ограниченное техническое обслуживание. Этот документ отвечает на вопрос **как устроена система и где проходят границы доверия**. Команды локального запуска — в [DEVELOPMENT.md](DEVELOPMENT.md), выпуска — в [DEPLOYMENT.md](DEPLOYMENT.md), восстановления — в [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md).

## 1. Компоненты и запрос пользователя

```text
Telegram WebView / браузер
          │ HTTPS
          ▼
Cloudflare Tunnel
          │
          ▼
Nginx (статический React + reverse proxy + rate limits)
          │ /api/*
          ▼
FastAPI → auth/access/identity → catalog/inventory/procurement
          │                          │
          └──────────── SQLAlchemy async ──────────→ PostgreSQL
                                                       │
                                             transactional outbox
                                                       │
                                      Telegram / email workers
                                                       │
                                  Cloudflare Gateway / Microsoft Graph
```

`backend/app/main.py` создаёт FastAPI-приложение, проверяет production-конфигурацию, подключает `TrustedHostMiddleware`, регистрирует маршруты через `backend/app/api/router.py` и на время жизни приложения открывает async SQLAlchemy engine. Маршруты распределены между `auth`, `access`, административным `identity`, `catalog`, `inventory`, `procurement`, `telegram_bot` и `health`. В production Swagger/OpenAPI endpoints отключены. Для доступа снаружи backend не публикует host port: его вызывает только внутренний Nginx.

Frontend построен на React/TypeScript/Vite. Он получает JSON через API; прямых подключений к PostgreSQL не имеет. Внешний интерфейс не является источником истины ни для ролей, ни для доступного количества. Postgres 18 развёрнут отдельным сервисом Docker Compose. Alembic управляет схемой, а отдельный шаг `db-permissions` применяет least-privilege права runtime identities после миграции.

## 2. Аутентификация и авторизация

При входе клиент передаёт Telegram `initData` в `/api/auth/telegram`. Backend сверяет криптографическую подпись и срок действия, связывает TelegramIdentity с User и выдаёт серверную сессию через HttpOnly cookie. При последующих запросах backend проверяет сессию, статус доступа и capability. Статус `PENDING`/`APPROVED`/`REJECTED`/`BLOCKED` хранится отдельно от роли; скрытие кнопки в React не даёт доступ к API.

Source roles: `ENGINEER`, `SENIOR_ENGINEER`, `MANAGER`, `ADMIN`, `OWNER`. Список capabilities задаёт серверная политика, а не числовое сравнение ролей: MANAGER — отдельная предметная ветка. OWNER — единственная recovery-identity, не назначаемая обычным API. Изменения доступа и ролей имеют транзакционный audit; custody и доступ сотрудника согласованы блокировками PostgreSQL. Полная матрица и порядок смены OWNER — в [RBAC_PROCUREMENT.md](RBAC_PROCUREMENT.md).

## 3. Каталог: номенклатура, не экземпляры

`Category` образует фиксированную и версионированную иерархию family → leaf. `Item` относится только к листу и содержит технические характеристики из типизированных EAV-записей. Нормализация имени, модели и сигнатуры позиции защищена на уровне приложения и PostgreSQL; изменение схемы категорий требует миграции. Технические характеристики и каноническая сигнатура **не** равны текущему количеству.

Поиск, выборка и фасеты работают в контексте выбранной категории, поисковой строки и производной области. `CatalogQuerySpec` содержит параметры отбора и metadata; сервер выполняет сортировку/пагинацию, а наличие на складе получает из складских проекций. Frontend не предполагает, что первая страница API содержит весь каталог. Для трансиверов производная область «Дальние» основана на нормализованной дальности, не является отдельной категорией. Поля и правила идентификации — в [CATALOG_SCHEMA.md](CATALOG_SCHEMA.md).

## 4. Склад: журнал и проекции

История изменений хранится в неизменяемых `Movement` и `MovementLine`. Актуальное состояние выводится транзакционно в двух проекциях:

```text
stock_balances(Item, Location, quantity)
user_item_custody_balances(User, Item, quantity)
```

`actor_user_id` означает исполнителя операции; `custody_user_id` — сотрудника, за которым числится агрегированное количество. Выдача/возврат ENGINEER или SENIOR_ENGINEER изменяет его custody; административные движения ADMIN/OWNER не создают персональную ответственность автоматически. Нельзя получить отрицательный остаток/custody, а нулевые строки не сохраняются. Активного жизненного цикла отдельного serial/WWN оборудования нет.

Запись операции идёт в одной транзакции: нормализация `client_request_id` → advisory lock и проверка idempotent replay/fingerprint → блокировка затронутого движения, пользователя, локаций, Item и balance rows в согласованном порядке → запись Movement/lines, пересчёт stock/custody и запись notification outbox → COMMIT. Совпадающий повтор запроса возвращает исходное движение, несовместимые данные — conflict; любая ошибка откатывает все предметные записи. Движения поддерживают RECEIPT, ISSUE, RETURN, TRANSFER, WRITE_OFF, CORRECTION, REVERSAL с различными правилами. Финальный procurement RECEIPT нельзя отменить обычным CORRECTION/REVERSAL.

Журнал читается через серверный MVCC snapshot и HMAC-подписанный opaque cursor, связанный с пользователем и фильтрами. Клиент не получает права задавать произвольные внутренние `snapshot_at` или `before_journal_seq`. Read-only `backend/scripts/reconcile_inventory_projections.sql` пересчитывает stock/custody по журналу; нулевое число строк результата означает отсутствие найденного дрейфа. Полный контракт — [WAREHOUSE_DOMAIN.md](WAREHOUSE_DOMAIN.md).

## 5. Закупки: отдельный жизненный цикл

`ProcurementRequest` хранит текущий статус, активную immutable revision, позиции и историю immutable events. Назначенный Manager отвечает за заявку, но это не ACL: допущенные MANAGER могут работать с активными заявками в рамках общей серверной политики. Предложенная позиция не создаёт Item автоматически. Согласование, возврат на корректировку, выбор менеджера, расхождения и передача на приёмку не меняют склад.

При окончательной технической приёмке сервер блокирует закупку, повторно проверяет статус, текущую revision, связи позиций с Item и локацию; в **той же транзакции** создаёт один Warehouse RECEIPT, связывает `final_movement_id`, записывает событие/уведомления и переводит заявку в `COMPLETED`. Уникальность финальной операции и неизменяемость истории защищены также DB-инвариантами текущих миграций. Partial acceptance текущая версия не предусматривает. Подробности — [RBAC_PROCUREMENT.md](RBAC_PROCUREMENT.md).

## 6. Уведомления и внешние границы

API не вызывает Telegram Bot API или Microsoft Graph в середине складской/закупочной транзакции. Вместо этого он записывает intent в PostgreSQL outbox с детерминированным dedupe key. Отдельный worker забирает сообщение по lease/claim, отправляет и фиксирует результат либо retry/DEAD. `/start` welcome проверяет актуальность claim token до изменения состояния чата и сохраняет результат в согласованной БД-транзакции.

Входящие Telegram updates проходят webhook secret и dedupe. Исходящие запросы Telegram worker направляет в Cloudflare Worker Gateway по HTTPS; Bot API token находится в отдельной доверенной границе. Email worker опционален, использует Microsoft Graph и отдельные права PostgreSQL; `EMAIL_DELIVERY_ENABLED=false` по умолчанию. Внешняя отправка **at-least-once**: outbox исключает дублирование намерений при replay, но при потерянном подтверждении Gateway/Graph возможно повторное внешнее сообщение. Exactly-once для такой границы не заявляется.

## 7. Frontend: скорость не меняет доверие

React access shell появляется без ожидания загрузки Telegram SDK. Проверка cookie-сессии и загрузка route chunk могут идти параллельно; unauthenticated Telegram auth exchange требует корректного контекста SDK. После APPROVED прогреваются несколько фиксированных lazy-маршрутов. Список каталога может загружаться параллельно метаданным leaf, а карточка Item сначала отображает placeholder из списка и затем перепроверяется каноническим endpoint. Query cache — только в памяти. Это оптимизация порядка запросов, а не обход access gate. Визуальные компоненты принадлежат `shared/ui`; детали — в [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md) и [FRONTEND_PERFORMANCE.md](FRONTEND_PERFORMANCE.md).

## 8. Ingress и сетевое доверие

В текущем исходном `frontend/nginx.conf` разделены недоверенный TCP `:8080` и доверенный Unix `/run/dc-inventory/ingress.sock`. На TCP Nginx не принимает чужие IP/proto headers как истину. На Unix использует `set_real_ip_from unix:` и `real_ip_header CF-Connecting-IP`, нормализует адрес для per-client rate limit и передаёт backend HTTPS-схему. Доверие к Unix-входу требует ограниченного host-каталога и проверенных UID/GID; права только самого socket недостаточны.

По последней документированной production-проверке Cloudflare Tunnel всё ещё направлен на `http://localhost:8080`. Развёртывание нового web-образа с этим старым origin запрещено: клиенты могут разделить один rate-limit bucket. CP-07 production migration остаётся открытой; совместное переключение, реальные права и rollback описаны в [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md).

## 9. Безопасность данных, provenance и восстановление

Образы содержат label `org.opencontainers.image.revision`. Проверка runtime provenance сравнивает заявленный checkout SHA с реальным HEAD и отдельно считывает immutable image ID/revision из **образа**, а не только из контейнерных labels. Документационный source-only sync может изменить Git HEAD без пересборки image при неизменном runtime source/контексте сборки. `ops/release/build_release.py` публикует release artifacts только после проверки полного набора. Git push не мигрирует БД и не разворачивает образы.

Initial production inventory был выполнен один раз через `app.bootstrap.production_inventory`: внешний workbook, closed gate, пустой Warehouse domain, существующий APPROVED ADMIN, одна транзакция создания локации и opening RECEIPT, контроль counts и zero-drift до COMMIT. Повторный bootstrap запрещён. Обычная граница — `REAL_INVENTORY_MUTATIONS_ENABLED`. Production default остаётся `false`.

Восстановление проводится по manifest, проверенному dump и точному application artifact в изолированной БД. SQL сверки должен соответствовать restored schema и извлекаться из exact backend image backup, а не из произвольно более нового checkout. CP-11 real S3 rehearsal, права БД CP-09, provenance CP-10 и реальная delivery CP-08 требуют отдельных production-подтверждений. Текущий source head — `b0c1d2e3f4a5`, последний документированный production head — `c3d4e5f6a7b8`; изменение документации не меняет эту разницу. Статусы и доказательства — [AUDIT_0_12_REMEDIATION.md](AUDIT_0_12_REMEDIATION.md).
