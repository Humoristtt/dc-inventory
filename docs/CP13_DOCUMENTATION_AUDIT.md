# CP-13 — документация: аудит и границы завершения

Дата: 19.09.2026. Основа: `remediation/audit-0-12` на `7e4c66d272e215354477e7674f5bf9a106258bf9`.

Статус: `IN_PROGRESS`. В GitHub пересмотрена карта Markdown и подготовлены изменения действующих документов; автоматические проверки нового коммита и production-приёмка на момент этой записи не выполнялись. Запрещено считать CP-13 завершённым только потому, что изменения опубликованы.

## Объём

На исходном SHA обнаружены 20 tracked Markdown: `AGENTS.md`, `README.md` и 18 файлов `docs/*.md`. Два новых файла этого прохода — `docs/README.md` (карта/ownership) и данный отчёт. Уникальные historical snapshots не редактируются задним числом. `AGENTS.md` — инструкции разработки; не меняется без нарушения конкретного правила.

## Расхождения с проверенными исходниками и ledger

1. В действующих README, архитектуре, development/deployment/operations, warehouse/RBAC и roadmap фигурировал устаревший source Alembic head `d4e5f6a7b8c9`. В миграционном графе присутствует последняя `a9c0d1e2f3a4`; её parent — `f8b9c0d1e2f3`. Последний документированный production Alembic `c3d4e5f6a7b8` сохраняется как отдельный факт, **не** как сегодняшняя live-проверка.
2. В roadmap и корневом README не были отражены CP-07–CP-12 и текущая последовательность CP-13→CP-18; source код и production acceptance смешивались.
3. Operations ошибочно описывал четыре DB identity при наличии owner/backend/Telegram/email/maintenance (пять). CP-09 применяет DB rights транзакционно и завершает legacy sessions отдельным post-commit вызовом.
4. Для CP-07 требуется атомарно согласованное переключение Cloudflare Tunnel origin с прежнего TCP на trusted Unix ingress вместе с web image; доступ UID/GID/cloudflared и права bind mount ещё не приняты на production. Нельзя выпускать новый web с прежним TCP Tunnel origin.
5. CP-10 добавил проверку заявленного checkout SHA против реального HEAD и атомарную публикацию release artifacts. Допустимый docs/host-tools-only sync может иметь image revision, отличный от HEAD, при неизменных build contexts и runtime source.
6. CP-11 проверяет manifest/dump size/hash/runtime/labels, isolated cleanup и отзыв восстановленных auth sessions. Повторный настоящий production-S3 restore и восстановление внешних конфигураций **открыты**.
7. В README/ROADMAP/доменной документации требовалось отделить historical accepted Warehouse/Procurement от текущего remediation branch, уточнить guarded one-shot bootstrap, закрытый regular mutation gate, custody и защищённый final procurement RECEIPT.

## Архитектурная нормализация

Создана `docs/README.md` с однозначными владельцами документационных контрактов, правилами выбора текущих и исторических источников, таблицей зависимостей, ссылками на все Markdown и критерием удаления. Корневой README — обзор; ROADMAP — состояние и порядок; AUDIT_0_12_REMEDIATION — полный журнал, ARCHITECTURE — устройство, доменные файлы — invariants, DEVELOPMENT — разработка, DEPLOYMENT — выпуск, OPERATIONS — эксплуатация, RECOVERY_RUNBOOK — восстановление.

Текущие повторяющиеся описания в девяти документах нормализованы и сведены к ссылкам на owner-файлы; никто не удаляет уникальные исторические доказательства ради сокращения текста. Исторические `HISTORY.md`, `STAGE15_PLAN.md`, `STAGE15_AUDIT_REMEDIATION.md`, `CATALOG_SOURCE_REFERENCE.md`, `FRONTEND_PERFORMANCE.md` оставлены: это не мусор, а отдельные датированные evidence. `CATALOG_SCHEMA.md`, `FRONTEND_DESIGN_SYSTEM.md`, `CP07_HTTP_SOCKET_MIGRATION.md`, `RECOVERY_RUNBOOK.md` проверены как собственные действующие контракты и не объединяются со смежными файлами без потери независимой области ответственности.

## Файлы с переработанным содержанием

- `README.md` — сводка с явными source/production границами и ссылками.
- `docs/ARCHITECTURE.md` — модули, data/auth, ingress, workers, provenance.
- `docs/DEVELOPMENT.md` — локальная установка, disposable DB, реальные и synthetic gate, source SHA.
- `docs/DEPLOYMENT.md` — release, CP-07, secrets/DB identities, миграции/rollback, operator acceptance.
- `docs/OPERATIONS.md` — текущие/исторические факты, 5 DB roles, health, Telegram, backup/DR.
- `docs/PRODUCT_REQUIREMENTS.md` — роли, stock/custody, procurement и bootstrap.
- `docs/RBAC_PROCUREMENT.md` — role matrix и state machine, external at-least-once.
- `docs/ROADMAP.md` — CP-00–18 и зависимости production acceptance.
- `docs/WAREHOUSE_DOMAIN.md` — транзакционные invariants, защищённый final RECEIPT, reconciliation.

Новое: `docs/README.md` и `ops/tests/test_docs_structure.py`. Тест проверяет, что каждый tracked Markdown включён в карту и ссылки существуют; не подменяет содержательный аудит.

## Обязательная приёмка перед CLOSED

- На опубликованном коммите запустить `python3 ops/tests/test_docs_freshness.py`, `python3 ops/tests/test_docs_structure.py`, `python3 ops/tests/test_notification_delivery_contract.py`, `python3 ops/tests/test_recovery_runbook_contract.py`, `git diff --check`. Исправить любые failures.
- В `docs/AUDIT_0_12_REMEDIATION.md` обновить устаревший `Current next action: CP-06` на CP-14 после подтверждённой приёмки документации и вписать уже существующий CP-11 commit `377f9a0e59e9f62684242a2b54f622536a52817d`. Этот старый журнал нельзя кратко переписать с потерей CP-00–06 evidence.
- До нового production окна не менять зафиксированные исторические production SHA/head, не закрывать CP-07–11 gates, CP-16/17 и новый S3 rehearsal.
- GitHub connector только создаёт Git objects/commit и не запускает локальные тесты. Push в remediation branch сам по себе не запускает CI: в `.github/workflows/ci.yml` push привязан к `main`, также есть PR, schedule и manual dispatch.

Этот отчёт описывает выполненную source-документационную работу и открытые проверки, а не обещает результат tests/production.
