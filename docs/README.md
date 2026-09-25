# Карта документации Spikatel Inventory

Актуально для `main` / production baseline `593ddec0c9100b0df2eafe4f324c7bb600d75cba` на 25.09.2026. Этот файл — **оглавление и правило выбора источника истины**, а не ещё одна копия требований, архитектуры или runbook. Начальная точка проекта: [README в корне](../README.md). Правила работы с репозиторием: [AGENTS.md](../AGENTS.md).

## 1. Как читать документацию

1. **Понять текущее состояние:** корневой README → [ROADMAP](ROADMAP.md) → [журнал CP-00–18](AUDIT_0_12_REMEDIATION.md). Статус `OPEN` в журнале имеет приоритет над общими фразами «реализовано» в предметных документах.
2. **Разрабатывать:** [ARCHITECTURE](ARCHITECTURE.md) → профильный предметный контракт → [DEVELOPMENT](DEVELOPMENT.md). Реальная реализация и миграции — окончательный технический источник при расхождении с документацией; найденное расхождение необходимо исправить.
3. **Развёртывать:** [DEPLOYMENT](DEPLOYMENT.md) → [OPERATIONS](OPERATIONS.md). Для смены HTTP ingress дополнительно обязателен [план CP-07](CP07_HTTP_SOCKET_MIGRATION.md); для восстановления — [RECOVERY_RUNBOOK](RECOVERY_RUNBOOK.md).
4. **Проверять прошлые решения:** [HISTORY](HISTORY.md) и датированные архивные материалы. Их старые значения миграций, состояния инфраструктуры и решения нельзя механически превращать в нынешние факты.

Различайте три сущности: состояние исходников и миграционного графа; **последний документально подтверждённый** production checkout/schema/runtime; фактическое состояние production **в момент новой проверки**. Git push сам по себе не обновляет контейнеры или БД. На 25.09.2026 подтверждены production revision `593ddec0c9100b0df2eafe4f324c7bb600d75cba` и Alembic `b0c1d2e3f4a5`; это датированное evidence, а не live monitoring. Защита штатных складских операций `REAL_INVENTORY_MUTATIONS_ENABLED=false` не отменяет выполненный ранее одноразовый bootstrap.

## 2. Нормативные документы: один владелец каждого контракта

| Файл | Что именно в нём искать | Не дублировать в других файлах |
|---|---|---|
| [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | Функциональные требования, роли пользователей, бизнес-сценарии, ограничения MVP | Условия доставки и команды production deployment |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Компоненты, границы доверия, транзакции, схема взаимодействия и provenance | Пошаговые команды оператора |
| [CATALOG_SCHEMA.md](CATALOG_SCHEMA.md) | Таксономия family/leaf, технические атрибуты, identity, facets | Исторические данные Excel |
| [WAREHOUSE_DOMAIN.md](WAREHOUSE_DOMAIN.md) | Item/Location, stock и custody, immutable movements, locks, idempotency, reconciliation | RBAC-матрица Procurement целиком |
| [RBAC_PROCUREMENT.md](RBAC_PROCUREMENT.md) | Полная матрица capabilities, OWNER, статусы закупок, immutable revisions, technical acceptance и уведомления | Общий операторский deploy runbook |
| [FRONTEND_DESIGN_SYSTEM.md](FRONTEND_DESIGN_SYSTEM.md) | Нормативные UI primitives, CSS ownership, responsive tokens, visual acceptance | Историю попыток оптимизации |

## 3. Реализация, эксплуатация и приёмка

| Файл | Ответственность |
|---|---|
| [DEVELOPMENT.md](DEVELOPMENT.md) | Версии инструментов, локальный запуск, disposable PostgreSQL, миграции, focused/fullstack tests, безопасный Git workflow |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Release artifacts, immutable SHA/image labels, секреты, границы миграций, точный порядок controlled deployment и rollback |
| [OPERATIONS.md](OPERATIONS.md) | Подтверждённые и неподтверждённые production facts, роли БД, health, workers, мониторинг, retention, S3/backup, smoke |
| [RECOVERY_RUNBOOK.md](RECOVERY_RUNBOOK.md) | Изолированное восстановление, проверка manifest/dump, exact image и schema-matched reconciliation, критерии остановки |
| [CP07_HTTP_SOCKET_MIGRATION.md](CP07_HTTP_SOCKET_MIGRATION.md) | История и итог production ingress migration: direct user ingress через host Nginx/Unix socket и отдельный Cloudflare Tunnel только для Telegram webhook |
| [ROADMAP.md](ROADMAP.md) | Текущая последовательность работ и отличие локального PASS от production acceptance |
| [AUDIT_0_12_REMEDIATION.md](AUDIT_0_12_REMEDIATION.md) | Подробный непрерывный журнал CP-00–18, коммиты, тесты, открытые условия; не переписывать историю чекпойнтов краткой сводкой |
| [MASTER_REMEDIATION_PLAN.md](MASTER_REMEDIATION_PLAN.md) | Сводный порядок устранения замечаний 12 аудитов; фактические результаты и evidence — в CP-журнале |
| [CP13_DOCUMENTATION_AUDIT.md](CP13_DOCUMENTATION_AUDIT.md) | Объём текущего аудита, найденные несоответствия, результаты/ограничения проверки |

Для production нельзя подменять [DEPLOYMENT](DEPLOYMENT.md) общими командами из [DEVELOPMENT](DEVELOPMENT.md). Для DR нельзя считать исторически успешный Stage15B доказательством нового реального восстановления после CP-11.

## 4. Исторические и справочные документы: сохранить, не объявлять действующими инструкциями

| Файл | Почему сохраняем |
|---|---|
| [HISTORY.md](HISTORY.md) | Хронология принятых решений и фактические исторические evidence, в том числе конкретные SHA и предыдущие релизы |
| [STAGE15_PLAN.md](STAGE15_PLAN.md) | Датированный протокол Stage 15 до ввода реального склада; pre-data assumptions внутри него относятся **только к тому моменту** |
| [STAGE15_AUDIT_REMEDIATION.md](STAGE15_AUDIT_REMEDIATION.md) | Отдельные AUD-00–24, исходные результаты и закрытие предыдущего этапа; номера AUD не тождественны нынешним CP-00–18 |
| [CATALOG_SOURCE_REFERENCE.md](CATALOG_SOURCE_REFERENCE.md) | Историческая сверка Stage 5 с локальными примерами; не является текущей схемой или источником реального inventory |
| [FRONTEND_PERFORMANCE.md](FRONTEND_PERFORMANCE.md) | Архитектурные решения и историческая проверка frontend performance; дата и SHA описывают тот релиз, а не сегодняшний runtime |

Старые фрагменты про `USER/ADMIN`, прежние Alembic heads, первоначальное отсутствие authoritative workbook и закрытый pre-data gate в этих файлах — датированная история. **Не удалять такие записи глобальной заменой.** Утверждения о текущем состоянии принадлежат README/ROADMAP/OPERATIONS и требуют свежего доказательства.

### Provenance внешних компонентов

| Файл | Назначение |
|---|---|
| [frontend/vendor/telegram-web-app.SOURCE.md](../frontend/vendor/telegram-web-app.SOURCE.md) | Происхождение vendored Telegram Web App SDK, зафиксированные upstream URL, дата получения, SHA-256 и требования к проверке при обновлении; не является инструкцией по развёртыванию и не подтверждает текущую версию SDK в работающем production. |

## 5. Архитектура документации и удаление дублей

- Корневой `README.md` — только назначение, ключевые invariants, состояние контуров и ссылки. Не второй операционный runbook.
- `ROADMAP.md` — последовательность и acceptance; детальные команды/тестовые логи — в CP-журнале и профильных файлах.
- `ARCHITECTURE.md` отвечает «как устроено и почему», `DEPLOYMENT.md` — «как безопасно выпустить», `OPERATIONS.md` — «как проверить и сопровождать»; решения о данных принадлежат domain docs.
- `HISTORY.md` — append-only evidence прошлых дат; новый факт добавляется датированно, а не заменяет старый.
- Файлы Stage 15, Stage 5 и старой frontend performance **не являются мусором**: они содержат уникальные evidence и ссылки из действующих контрактов/тестов. До перепроверки всех ссылок и переноса уникальных сведений физическое удаление или переименование небезопасно. Логическое объединение повторяющихся текущих описаний — через единые канонические документы и ссылки выше, без потери исторических фактов.
- Новые Markdown добавляются только при отдельной области ответственности; одновременно обновляются эта карта, ссылка из канонического документа и, если затронуты состояния, CP-журнал.

## 6. Достоверность и проверки

Источник текущих технических фактов — `backend/`, `frontend/`, `compose.yaml`, `ops/`, миграции и регрессионные тесты. Проверять `python3 ops/tests/test_docs_freshness.py`, `python3 ops/tests/test_notification_delivery_contract.py`, `python3 ops/tests/test_recovery_runbook_contract.py`, `python3 ops/tests/test_docs_structure.py` и `git diff --check` на актуальном checkout. CP-16 production deployment и CP-17 real Telegram acceptance уже имеют production evidence; следующий независимый gate — CP-18.

Секреты, реальные inventory dataset/workbook, dumps, `.env` и private/runtime-only IDs в публичный Git не помещать. Восстановление, миграции, Cloudflare/Tunnel и live Telegram/email требуют отдельных разрешённых операций, а не выполняются в рамках редактирования документации.
