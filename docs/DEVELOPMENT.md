# Разработка и локальные проверки

Разработку ведём на Mac в отдельном checkout. Production VM не используем как среду разработки и не направляем на неё локальные миграции, SQL или тесты. Этот документ отвечает за настройку и безопасный запуск; устройство модулей — в [ARCHITECTURE.md](ARCHITECTURE.md), правила склада — в [WAREHOUSE_DOMAIN.md](WAREHOUSE_DOMAIN.md), ролей и закупок — в [RBAC_PROCUREMENT.md](RBAC_PROCUREMENT.md).

## 1. Инструменты и установка

Нужны Python 3.12, Node.js 24, Docker Engine/Compose и Git. Для backend создаём виртуальное окружение в `backend/.venv` и устанавливаем зафиксированные зависимости:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
```

`requirements-dev.lock` должен соответствовать `pyproject.toml`; при изменении зависимостей обновляем lock и проверяем чистую установку с `--require-hashes`. Окружение `.venv` не добавляем в Git.

Для frontend:

```bash
cd frontend
npm ci
npx playwright install chromium webkit
npm run dev
```

Зависимости устанавливаем по `package-lock.json`; не используем произвольное обновление пакетов как побочный эффект работы над документацией.

## 2. Локальная конфигурация и PostgreSQL

Создаём локальный `.env` по `.env.example`. В Git не помещаем `.env`, токены, дампы, реальные инвентарные таблицы и секреты. Dev Compose: `compose.dev.yaml`; он публикует PostgreSQL **только на loopback** через порт `${POSTGRES_DEV_PORT:-55432}`, а внутренние backend/DB соединения использует через Docker `db_net`. Web не подключается к БД напрямую.

```bash
# Из корня репозитория

docker compose --env-file .env -f compose.dev.yaml up -d --wait postgres
```

Для ручного запуска backend/миграций на Mac нужен URL с `127.0.0.1`, а не Docker hostname `postgres`:

```bash
set -a
source .env
set +a
HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_DEV_PORT:-55432}/${POSTGRES_DB}"
```

**Внимание:** эта команда лишь формирует URL. Прежде чем выполнять любую миграцию, убедитесь, что выбранная БД — выделенная dev/test БД, а не production или общая рабочая БД. Не выводите строку с паролем в логи и не копируйте её в переписку.

```bash
cd backend
DATABASE_URL="$HOST_DATABASE_URL" APP_ENV=development .venv/bin/alembic upgrade head
DATABASE_URL="$HOST_DATABASE_URL" APP_ENV=development .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Backend предоставляет `/api/health/live` и `/api/health/ready`; Swagger `/api/docs` доступен вне production. Для запуска dev Compose целиком из корня:

```bash
docker compose --env-file .env -f compose.dev.yaml up -d --build --wait web
```

Локальный web доступен на `http://127.0.0.1:8080`. Это не production release и не подтверждение доступности Telegram Tunnel.

## 3. Версия БД и миграции

Базовая миграция: `48c2f07f01a0`. Текущий **исходный** Alembic head: `b0c1d2e3f4a5`. Последний документированный production Alembic head: `c3d4e5f6a7b8`; фактическое значение на сервере перед CP-16 проверяется повторно. Разница этих двух значений не устраняется `git pull` или синхронизацией документации.

Исторические миграции не переписываем. Новая миграция должна быть детерминированной, иметь ограничения и безопасный порядок downgrade. Миграции с несовместимым форматом данных нельзя откатывать без проверки guard; для SFP downgrade предусмотрен специальный CI gate. Подробный порядок production cutover — только в [DEPLOYMENT.md](DEPLOYMENT.md).

## 4. Backend-проверки

Выполняем из `backend`:

```bash
.venv/bin/ruff check app tests migrations
.venv/bin/mypy app tests migrations/env.py migrations/versions
.venv/bin/pytest -q
```

PostgreSQL integration suite включается только при `RUN_POSTGRES_INTEGRATION=1`, с URL **заранее созданной и мигрированной одноразовой БД**. Не назначаем этот флаг базе с реальными данными. Отдельная проверка разрушительного SFP downgrade использует `RUN_SFP_DOWNGRADE_POSTGRES=1` и `tests/test_sfp_migration_downgrade_postgres.py` исключительно в собственном изолированном контуре. Исторические результаты запуска не заменяют новый прогон после изменений backend.

Профильные проверки по необходимости: `tests/test_catalog_postgres.py`, `tests/test_catalog_api_postgres.py`, `tests/test_inventory_postgres.py`, `tests/test_inventory_api_postgres.py`, `tests/test_runtime_database_role_contract.py`. Изменения ролей должны отдельно подтверждать защиту журнала от UPDATE/DELETE, ограниченные права workers, аудит доступа, recovery и DB-инварианты. Не проверяем безопасность только скрытием кнопок в React.

## 5. Frontend и браузерные тесты

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`frontend/e2e/warehouse-v2.spec.ts` и предметные UI-тесты применяют синтетические Telegram/API fixtures, в том числе для мобильных и desktop-профилей. Это проверки интерфейса, **не** подтверждение настоящих PostgreSQL side effects. Отдельного пользовательского экрана «Моё оборудование» нет; custody является backend integrity projection.

Для полного локального сценария с настоящими HTTP API и PostgreSQL используем только штатный runner из `ops/tests/run_fullstack_local.sh`:

```bash
cd frontend
npm run test:e2e:fullstack:local
```

Runner читает локальный `.env`, создаёт уникальную БД `dc_inventory_fullstack_*`, проверяет соответствие Compose-контейнера и loopback-порта, создаёт случайный маркер и **до первой миграции** сверяет его через реальное TCP-подключение backend. После этого выполняет Alembic, запускает отдельные backend/Vite, применяет подписанный синтетический Telegram `initData`, временно разрешает мутации только дочерним тестовым процессам и запускает `npm run test:e2e:fullstack`. В конце сверяет предметное состояние и `backend/scripts/reconcile_inventory_projections.sql`, останавливает свои процессы и удаляет созданную БД.

Маркер, топология, DB URL и удаление защищены `ops/tests/fullstack_db_guard.py`; его отрицательные регрессии находятся в `ops/tests/test_fullstack_db_guard.py`, текстовый контракт — в `ops/tests/test_fullstack_e2e_contract.py`. Для нового запуска нужны `FULLSTACK_POSTGRES_TOPOLOGY=PASS`, `FULLSTACK_PREMIGRATION_DATABASE=PASS` **до Alembic**, успешный Playwright и `FULLSTACK_DATABASE_CLEANUP=PASS`. Не запускайте эти сценарии через вручную загруженный `.env.fullstack` и не переносите переменные разрешения мутаций в текущую оболочку. При неуспешном cleanup проверяйте только названную тестовую БД, не выполняя массовые удаления.

CI отдельно выполняет `npm run test:e2e:fullstack` в production-shaped Compose. Синтетический Telegram контекст допускается, но HTTP API не мокается. Этот сценарий не заменяет реальную Telegram-приёмку после развёртывания.

## 6. Сверка данных и health

Read-only `backend/scripts/reconcile_inventory_projections.sql` пересчитывает stock/custody из неизменяемого журнала. Нормальный результат — ноль строк; любое отклонение требует остановки опасных операций, сохранения доказательств и расследования, а не автоматического исправления остатков. После миграций Warehouse, восстановления и рискованного обслуживания БД сверка обязательна.

Health regression: при рабочем PostgreSQL `live/ready = 200/200`; при его недоступности — `200/503`; после восстановления — `200/200` без перезапуска backend. Initial production bootstrap уже выполнялся однократно; повторный импорт через `app.bootstrap.production_inventory` запрещён, реальные workbook и значения остаются вне Git. Последний документированный штатный gate — `REAL_INVENTORY_MUTATIONS_ENABLED=false`.

## 7. Git, проверки и выпуск

Путь изменений: Mac → разрешённый push в GitHub → проверенный точный SHA и CI → отдельно согласованный production release. Сборка runtime image маркируется `APP_REVISION="$(git rev-parse HEAD)"`; OCI label `org.opencontainers.image.revision` проверяется по образу. `ops/release/build_release.py` публикует артефакты только после их проверки. Documentation/host-side `ops/` sync без пересборки допустим при неизменных runtime source и Docker build contexts, но host scripts требуют собственных проверок.

Не запускаем полный набор проверок после каждого файла: сначала профильная проверка изменённой области, затем один общий gate для итогового изменения. В рамках текущей документационной ревизии повторные проверки двенадцати разделов запланированы **после** сведения документации; прежние PASS нельзя выдавать за результат нового Git HEAD. Журнал: [AUDIT_0_12_REMEDIATION.md](AUDIT_0_12_REMEDIATION.md).
