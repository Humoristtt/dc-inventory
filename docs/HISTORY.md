# История проекта

Здесь фиксируются ключевые этапы развития проекта, инфраструктурные изменения и архитектурные решения.

## 2026-08-31 — Инициализация проекта

- Создан private-репозиторий `Humoristtt/dc-inventory`.
- Первый commit: `d889f3bcc4a31d9bd8660eb8827afad3e73fffe6`.
- Подготовлена production VM `dc-inventory` на Ubuntu Server 24.04.4 LTS.
- Выделено 4 vCPU, 8 GB RAM, 100 GB disk и 2 GB swap.
- Root filesystem расширен через LVM примерно до 98 GB.
- Настроен SSH только по ключу; password authentication и root login отключены.
- Настроен локальный SSH alias `ssh inventory`.
- Установлены Docker Engine, Docker Compose и containerd из официального Docker repository.
- Для Docker включены `live-restore` и ограничение размера container logs.
- Production VM получила отдельный read-only GitHub Deploy Key `dc-inventory-prod`.
- Проверен доступ к GitHub, Docker Hub и Cloudflare.
- Установлено, что прямое TCP-соединение VM к `api.telegram.org:443` завершается timeout до TLS handshake.
- Принято решение не направлять весь трафик VM через VPN/WARP; Telegram Bot API будет обслуживаться через отдельный безопасный gateway.
- Получены исходные Excel-файлы текущей складской номенклатуры.
- Получены фирменный guidebook Spikatel 2026 и оригинальные web-логотипы.
- Документация проекта ведётся на русском языке и должна обновляться вместе с реализацией.

## 2026-08-31 — Backend runtime foundation

- Создан backend foundation на Python 3.12 и FastAPI.
- Зафиксирован архитектурный стиль модульного монолита.
- Выделены инфраструктурные слои `api`, `core`, `db` и каталог будущих предметных модулей `modules`.
- Настроен SQLAlchemy 2 в async-режиме через `asyncpg`.
- Добавлена обязательная конфигурация `DATABASE_URL`.
- Добавлен ограниченный timeout подключения к PostgreSQL.
- Настроен Alembic в async-режиме.
- Строка подключения к PostgreSQL не хранится в `alembic.ini`.
- Создан baseline Alembic `48c2f07f01a0`.
- Добавлен PostgreSQL 18 для локальной разработки через `compose.dev.yaml`.
- Development PostgreSQL публикуется только на `127.0.0.1:55432`.
- Локальный `.env` исключён из Git; добавлен `.env.example`.
- Реализован `/api/health/live`.
- Реализован `/api/health/ready` с реальной проверкой PostgreSQL.
- DB health logic вынесена из HTTP-слоя в `app/db/health.py`.
- Настроены Ruff, mypy strict и Pytest.
- Unit tests проверяют успешный readiness и ответ HTTP 503 при недоступной БД.
- Выполнен acceptance с реальным PostgreSQL: `UP -> 200/200`, `DOWN -> 200/503`, `BACK -> 200/200`.
- Подтверждено восстановление readiness без рестарта backend.
- Для будущих автоматизированных runtime-проверок вместо фиксированных задержек будет использоваться bounded readiness polling.

## 2026-08-31 — Production-shaped runtime foundation

- Добавлен production Compose `compose.yaml`.
- В production на host публикуется только Nginx на `127.0.0.1:8080`.
- Backend и PostgreSQL не публикуют host-порты.
- Добавлен `requirements-dev.lock` с hash-locked development/CI-зависимостями.
- Добавлен GitHub Actions CI для backend, frontend, миграций и сборки Docker images.
- Удалены остаточные файлы стандартного Vite scaffold.
- Добавлена deployment-документация.

## 2026-08-31 — Архитектурный pre-feature hardening

- Проведён полный аудит runtime foundation перед Telegram authentication и первой предметной миграцией.
- Добавлен naming convention SQLAlchemy до появления предметных constraints.
- Зафиксированы DB pool, statement timeout и lock timeout boundaries.
- PostgreSQL runtime sessions закреплены в UTC.
- Production Swagger/OpenAPI отключены.
- Исправлена proxy-chain семантика Cloudflare -> Nginx -> Uvicorn для scheme и client IP.
- PostgreSQL изолирован от web отдельной internal Docker network.
- CI расширен production-shaped runtime smoke test через Nginx, FastAPI, Alembic и PostgreSQL.
- Обновлена canonical документация frontend/runtime/deployment.

## 2026-09-01 — Telegram identity, auth и access foundation

- `533a7b5` — User / TelegramIdentity / AccessRequest persistence.
- `c13f030` — Telegram initData validation, server-side AuthSession и auth API.
- `93490cd` — frontend auth gate, кликабельный `@Humoristttt`, access request и
  pending flow.
- Post-checkpoint audit выделил Stage 4.3a до outbox/webhook: retry после
  `REJECTED`, backend `Approved`/`Admin` boundary, bootstrap ADMIN consistency,
  PostgreSQL integration tests, Compose secret boundary и синхронизация docs.
- Повторный source audit Stage 4.3a выявил stale access-cache риск во frontend:
  access-state одного пользователя не должен иметь приоритет над свежим auth-state
  и не должен переиспользоваться между user ID.
- Stage 4.3b закрывает user-scoped access cache, PENDING-only frontend authority,
  реальный PostgreSQL race первого Telegram login и CI runtime network boundaries.
- Stage 4.4 начинается после полного gate Stage 4.3b.
## 2026-09-01 — Stage 4.4 — Telegram delivery и production access

- Реализован transactional `NotificationOutbox`.
- Добавлен отдельный `telegram-worker` с PostgreSQL claim/lease,
  `FOR UPDATE SKIP LOCKED`, bounded retry и `PENDING/SENT/DEAD` lifecycle.
- Реализован Telegram webhook с secret-token validation и persistent
  `TelegramUpdate.update_id` dedupe.
- Реализованы opaque ADMIN approve/reject callbacks.
- Решение доступа выполняется только `ADMIN + APPROVED`, транзакционно и
  идемпотентно; terminal user state не может быть переписан stale callback.
- После решения ADMIN inline-кнопки очищаются, пользователь получает
  Telegram-уведомление.
- Развёрнут отдельный Cloudflare Worker Telegram Gateway с gateway secret и
  фиксированным Bot API allowlist.
- Telegram webhook зарегистрирован на
  `https://app.spik-inventory.ru/api/telegram/webhook`.
- Реальный `sendMessage` через Gateway проверен.
- Production `/start` выявил Cloudflare `403 / 1010` для стандартного
  `Python-urllib` User-Agent до выполнения Worker.
- PR #6 добавил явный service User-Agent
  `dc-inventory-telegram-worker/1.0`; PR #7 исправил typing regression test,
  после чего полный CI прошёл успешно.
- Production runtime code обновлён до
  `08aa052d2af3e9c7e9cb9a2bce670cf6674b6c97`.
- Реальный `/start` проходит полный Telegram → webhook → FastAPI → outbox →
  worker → Cloudflare Gateway → Telegram маршрут.
- Production access smoke со вторым Telegram account завершён:
  request access → ADMIN notification → approve → user notification →
  успешный вход в Mini App.
- Production VM после закрытия runtime-этапа имеет чистый worktree, только
  локальную ветку `main` и не содержит untracked project files.
- Stage 4 production MVP завершён.
- Следующий предметный этап — Stage 5 Catalog Foundation.

## 2026-09-01 — Stage 5 — Catalog Foundation

- Добавлен предметный модуль `app/modules/catalog`.
- Реализованы Category, Manufacturer, Item, CategoryAttribute и typed
  ItemAttributeValue.
- Item закреплён как каталожная позиция, отдельная от будущего физического
  InventoryUnit.
- Добавлены QUANTITY/SERIAL defaults и ACTIVE/ARCHIVED lifecycle без публичного
  hard-delete.
- PostgreSQL enforcing включает exactly-one typed value, unique keys,
  normalized manufacturer/internal code и composite cross-category foreign keys.
- Реализована metadata-driven validation TEXT/INTEGER/DECIMAL/BOOLEAN/ENUM,
  required fields, allowed values, exact Decimal и canonical units.
- Добавлены non-destructive duplicate candidates по manufacturer part number
  либо exact normalized name/model.
- Добавлены Approved read API и Admin mutation API с immutable category и
  accounting mode, full-replacement PATCH semantics для attributes и
  idempotent archive/unarchive.
- Alembic revision `f4a5b6c7d8e9` version-controls пять system categories и их
  initial attributes.
- Добавлены focused domain, PostgreSQL 18, API и authorization tests.
- После независимого аудита Stage 5 regression tests отвязаны от глобального
  Alembic head и точного общего числа Category: они проверяют устойчивые
  свойства пяти initial system schemas и допускают будущие migrations/categories.
- DECIMAL validation приведена в точное соответствие `NUMERIC(30,10)`:
  максимум 20 integral и 10 fractional digits до persistence.
- ORM delete Manufacturer передан PostgreSQL `ON DELETE RESTRICT` через
  `passive_deletes="all"`; добавлен real-PostgreSQL regression test.
- Канонический contract зафиксирован в `docs/CATALOG_SCHEMA.md`.
- Source Excel/CSV в текущем workspace отсутствовал; соответствующие
  vocabularies оставлены provisional, production/source reconciliation не
  заявлена выполненной.
