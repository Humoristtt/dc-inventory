# Локальная разработка Spikatel Inventory

Документ описывает команды разработки и проверки **локального source**, а не текущую конфигурацию production. Каноническая архитектура: `docs/ARCHITECTURE.md`; требования ролей/закупок: `docs/RBAC_PROCUREMENT.md`; общее оформление: `docs/FRONTEND_DESIGN_SYSTEM.md`.

## Версии и установка

Нужны Python 3.12, Node.js 24, Docker Engine и Docker Compose. В `backend`:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
```

`requirements-dev.lock` обновляется при изменении `pyproject.toml`, затем проверяется чистой установкой с `--require-hashes`. Окружение `.venv` не коммитится.

Frontend:

```bash
cd frontend
npm ci
npm run dev
npm run lint
npm run typecheck
npm test
npm run build
npx playwright install chromium webkit
npm run test:e2e
```

Общие header, button, form-control и dialog primitives принадлежат `frontend/src/shared/ui`. Feature CSS отвечает за компоновку, а не за независимую геометрию базовых controls. Изменения visual contract сопровождаются обновлением design-system документа и регрессионных проверок.

## Конфигурация и безопасность

Локальный `.env` создаётся по `.env.example`; настоящие production secrets и datasets в Git не помещаются. Никогда не направляйте тесты на production или общую development DB. Production VM — не development environment.

Для RBAC/Procurement нельзя подменять backend authorization frontend-видимостью, считать MANAGER уровнем линейной иерархии, считать assigned Manager ACL, менять stock по статусу закупки, автоматически создавать Item из proposed line либо переписывать submitted revision. Читайте `docs/RBAC_PROCUREMENT.md` перед изменениями этих доменов.

## PostgreSQL и Alembic

Development PostgreSQL поднимается только на loopback через отдельный `dev_host_net`:

```bash
docker compose --env-file .env -f compose.dev.yaml up -d --wait postgres
```

Host port `127.0.0.1:55432`; backend и БД взаимодействуют внутри `db_net`, web к БД не подключается.

Для миграций с Mac:

```bash
set -a; source .env; set +a
HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"
cd backend
DATABASE_URL="$HOST_DATABASE_URL" alembic upgrade head
```

Baseline Alembic: `48c2f07f01a0`. Текущий source migration head: `a9c0d1e2f3a4`. Последний документированный running production migration head: `c3d4e5f6a7b8`; это разные контуры. Миграции `d4e5f6a7b8c9` … `a9c0d1e2f3a4` и исправления CP-07–12 не являются production state до отдельного deploy/provenance acceptance. Не выводите версию БД из Git HEAD.

## Локальный backend и полный dev runtime

```bash
set -a; source .env; set +a
HOST_DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:55432/${POSTGRES_DB}"
cd backend
DATABASE_URL="$HOST_DATABASE_URL" APP_ENV=development uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Endpoints: `/api/health/live`, `/api/health/ready`; Swagger только вне production: `http://127.0.0.1:8000/api/docs`.

Полный dev стек из корня:

```bash
docker compose --env-file .env -f compose.dev.yaml up -d --build --wait web
```

Публичный локальный entrypoint: `http://127.0.0.1:8080`. Backend/PostgreSQL host ports в production не публикуются. Dev `POSTGRES_DEV_PORT` позволяет использовать отдельный loopback-порт для одноразовой БД.

## Проверки

Backend из `backend`:

```bash
ruff check app tests migrations
mypy app tests migrations/env.py migrations/versions
pytest -q
```

PostgreSQL integration tests по умолчанию пропускаются и требуют **отдельной мигрированной disposable БД**:

```bash
RUN_POSTGRES_INTEGRATION=1 DATABASE_URL=postgresql+asyncpg://USER:PASS@127.0.0.1:PORT/TEST_DB pytest -q
```

Деструктивный SFP downgrade gate только на одноразовой БД:

```bash
RUN_SFP_DOWNGRADE_POSTGRES=1 DATABASE_URL=postgresql+asyncpg://USER:PASS@127.0.0.1:PORT/TEST_DB pytest -q tests/test_sfp_migration_downgrade_postgres.py
```

Focused проверки: `tests/test_catalog_postgres.py`, `tests/test_catalog_api_postgres.py`, `tests/test_inventory_postgres.py`, `tests/test_inventory_api_postgres.py`; для production roles — `tests/test_runtime_database_role_contract.py` и соответствующие integration tests. Тесты ролей обязаны проверять отсутствие broad journal UPDATE/DELETE, ограниченный UPDATE Telegram processed state, delivery recovery и изоляцию worker identities.

Frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

`frontend/e2e/warehouse-v2.spec.ts` использует synthetic Telegram/API fixtures, проверяет responsive/browser UX, но **не** является full-stack доказательством. Browser profiles: Telegram Desktop narrow, Android-like, iPhone-like, WebKit и desktop/admin. Отдельного active «Моё оборудование» UI нет; custody является backend integrity projection.

Для локального real API/DB browser gate:

```bash
cd frontend
npm run test:e2e:fullstack:local
```

Runner создаёт уникальную test DB, мигрирует до head, запускает временные backend/Vite процессы, применяет синтетический signed Telegram context, проверяет БД и удаляет свои ресурсы. Запрещено вручную `source`-ить `.env.fullstack` в интерактивную оболочку или запускать сценарий против общей БД. CI запускает `npm run test:e2e:fullstack` с production-shaped Compose: настоящий frontend → FastAPI → PostgreSQL, Telegram context синтетический, API не мокается.

Health regression: при PostgreSQL UP `live/ready=200/200`, DOWN `200/503`, BACK `200/200` без перезапуска backend. Для change set сначала focused checks, потом один affected full gate; CI — repository-wide gate. После каждого небольшого редактирования полный стек повторно не гоняется.

## Reconciliation и inventory safety

Read-only скрипт: `backend/scripts/reconcile_inventory_projections.sql`. Он сверяет stock и custody с immutable Movement/MovementLine journal; zero rows — норма. Любая строка — data-integrity blocker, а не приглашение автоматически пересоздать остатки. После warehouse migration, restore и risky data maintenance reconciliation обязателен. Regular production mutation gate независимо остаётся `REAL_INVENTORY_MUTATIONS_ENABLED=false`.

Initial production bootstrap завершён однократно. Валидатор `app.bootstrap.inventory_workbook` и guarded production CLI `app.bootstrap.production_inventory` — разные interfaces. Внешний workbook и реальные dataset values не хранятся в source.

## Git и release provenance

Путь: Mac → GitHub → проверенный exact commit/CI → production VM (read-only Deploy Key). Runtime-changing image build получает `APP_REVISION="$(git rev-parse HEAD)"`; OCI label `org.opencontainers.image.revision` проверяется по самому образу, а не только контейнеру. `ops/release/build_release.py` публикует manifest/env после валидации всех release images. Runtime provenance сравнивает заявленный checkout SHA с фактическим Git HEAD; source-only documentation/host-tools sync допускает отличающийся image revision при неизменных runtime source и Docker build contexts.

Production deployment, реальная доставka Telegram/email, восстановление S3 и live acceptance являются отдельными задачами; результаты локальных тестов их не заменяют. Текущий журнал: `docs/AUDIT_0_12_REMEDIATION.md`.
