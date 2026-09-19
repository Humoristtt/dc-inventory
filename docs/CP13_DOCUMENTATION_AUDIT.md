# CP-13 — ревизия документации и доказательства

**Дата:** 19.09.2026. **Контур:** `remediation/audit-0-12`. **Начальный SHA этой редакционной ревизии:** `38d1b19871da888128926bcdab72673b5beb7b8f`. **Статус:** `IN_PROGRESS` / в основном журнале `OPEN` до проверки опубликованного итогового коммита. Изменения выполняются непосредственно через GitHub; этот способ записи сам по себе **не запускает** локальные тесты или полный CI. Не объявляем CP-13 закрытым только по числу переписанных файлов.

## 1. Объём и метод

На исходном SHA — **23 tracked Markdown**, включая корневые `README.md`, `AGENTS.md`, карту `docs/README.md`, действующие технические контракты, исторические отчёты и provenance vendored Telegram SDK. Документы сверяем с фактическим `backend/`, `frontend/`, `compose.yaml`, миграциями и проверками. Последнюю документированную production-проверку не принимаем за live-состояние: source Alembic `a9c0d1e2f3a4`, production evidence `c3d4e5f6a7b8` — разные контуры. Значения SHA и схему production перед CP-16 требуется прочитать заново с целевой VM.

Каждому виду сведений назначен один владелец: [карта документации](README.md) определяет назначение каждого файла; корневой README объясняет проект; ARCHITECTURE — компоненты и доверие; предметные документы — инварианты; DEVELOPMENT — локальную работу; DEPLOYMENT — одобренный выпуск; OPERATIONS — диагностику; RECOVERY_RUNBOOK — изолированное восстановление; ROADMAP — порядок; AUDIT_0_12_REMEDIATION — фактические checkpoint evidence. Исторические файлы сохраняем, если там есть уникальные SHA, результаты и объяснение прежних решений. Наличие английских значений API, сущностей и переменных окружения не является основанием их переводить и ломать техническую идентичность.

## 2. Найденные проблемы и исправления

| Область | Выявленное расхождение | Как нормализовано |
|---|---|---|
| Общая документация | Повторение состояния в README, архитектуре, roadmap и operations; риск принять source за production. | Разделены назначение/устройство/порядок/последние факты. Датированные SHA и Alembic явно указаны как evidence. |
| Каталог | Старый Stage5 reference ссылался на поля и категории, отсутствующие в текущем `configuration.py`. | Действующая схема переписана по `LEAVES`, типам Attribute и `normalization.py`; reference оставлен отдельным историческим документом с явными отличиями. |
| Склад | История, количество, custody и физический экземпляр иногда описывались без ясной границы. | Отдельно описаны immutable Movement/Line, stock/custody, роль actor, locking, idempotency и zero-drift. Уточнено отсутствие active serial/WWN lifecycle. |
| RBAC/Procurement | Повторяющиеся описания прав, неполная граница между manager responsibility и ACL. | Матрица сверена с `identity/policy.py`; OWNER, access lifecycle, финальный RECEIPT и immutable revisions описаны вместе. |
| Full-stack | Прежняя инструкция не отражала исправление CP-15 перед миграцией. | DEVELOPMENT объясняет проверку Docker topology/nonce по TCP до Alembic, временный gate только в child processes, domain reconciliation и cleanup. |
| Ingress | Локальная реализация Unix-входа могла выглядеть как уже готовый production cutover. | CP-07 и DEPLOYMENT отдельно фиксируют текущий TCP Tunnel, требуемый host bind mount, UID/GID, доступ каталога и одновременный rollback web/Tunnel. |
| Backup/DR | Старые успешные восстановления могли ошибочно использоваться вместо свежего CP-11 rehearsal. | RECOVERY_RUNBOOK явно различает historical Stage15B, synthetic local tests и настоящий S3 replay; добавлены точный image/schema SQL, отзыв сессий и границы удаления ресурсов. |
| Frontend | Длинная смешанная русско-английская документация дублировала визуальные и performance решения. | Design-system определяет единственного владельца CSS; performance описывает последовательность загрузки и хранит старые замеры отдельно от текущего CP-14. |
| Engineering policy | `AGENTS.md` был англоязычным. | Переведён на русский с сохранением запрета несанкционированного deploy, push, merge, доступа к production и лишних повторных тестов. |

Отдельный технический факт CP-15: предыдущий full-stack runner проверял целевую БД **после миграции**. Коммит `38d1b19` добавил проверку экземпляра PostgreSQL и одноразовой БД **до миграции**. На этом коммите локально подтверждены topology/nonce PASS, два Playwright-теста, zero-drift и удаление БД. Это относится к коду runner, не означает завершение всех трёх проходов CP-15.

## 3. Переписанные и сохранённые материалы

В рамках текущего редакционного этапа переработаны с прямой опорой на прочитанные контракты:

- `README.md`, `AGENTS.md`;
- `docs/ARCHITECTURE.md`, `docs/PRODUCT_REQUIREMENTS.md`, `docs/CATALOG_SCHEMA.md`, `docs/WAREHOUSE_DOMAIN.md`, `docs/RBAC_PROCUREMENT.md`;
- `docs/DEVELOPMENT.md`, `docs/DEPLOYMENT.md`, `docs/OPERATIONS.md`, `docs/RECOVERY_RUNBOOK.md`, `docs/CP07_HTTP_SOCKET_MIGRATION.md`;
- `docs/FRONTEND_DESIGN_SYSTEM.md`, `docs/FRONTEND_PERFORMANCE.md`, `docs/CATALOG_SOURCE_REFERENCE.md`, `docs/ROADMAP.md`.

`docs/README.md` уже содержит карту всех Markdown и отдельные владельцы контрактов, поэтому дублировать её таблицы здесь не нужно. Исторические `docs/HISTORY.md`, `docs/STAGE15_PLAN.md`, `docs/STAGE15_AUDIT_REMEDIATION.md` и контрольный журнал `docs/AUDIT_0_12_REMEDIATION.md` **не заменяем короткой сводкой**: у них уникальные даты, SHA, исходные FAIL/PASS и checkpoints, на которые ссылаются технические тесты. Старые pre-data значения `CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED` и `REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP` в Stage15 относятся к конкретному прошлому моменту, а не к текущему складу. `frontend/vendor/telegram-web-app.SOURCE.md` содержит проверяемое происхождение внешнего runtime SDK; удалять его как «мусор» нельзя.

Физическое удаление файлов требует отдельного доказательства, что нет уникальных свидетельств, действующих ссылок и CI-контрактов. На этом этапе такого подтверждения **нет**, поэтому не удаляем архивы только ради сокращения числа Markdown.

## 4. Открытые замечания по source и production

- `docs/CP07_HTTP_SOCKET_MIGRATION.md`: в исходниках Nginx реализован Unix listener, но в прочитанном `compose.yaml` web ещё имеет только loopback-published TCP port и **не содержит готового host bind mount** для Unix-каталога. Это нужно включить в точный release plan, проверить у пользователя `cloudflared` и выполнить с согласованным переключением; документация не исправляет Compose автоматически.
- CP-08: live Telegram/Graph delivery, actual worker secrets и configuration acceptance открыты.
- CP-09: production transaction grant cutover и termination legacy sessions не выполнялись в рамках этой ревизии.
- CP-10: release provenance текущего живого runtime не проверялся на VM.
- CP-11: настоящий production-S3 rehearsal и внешняя конфигурация после локальных исправлений не проверялись.
- CP-12: сопровождаемость и production acceptance остаются предметом отдельного аудита.
- CP-15: помимо исправления runner, остальные проходы предрелизного аудита не завершены.

Regular warehouse gate по последнему evidence — `REAL_INVENTORY_MUTATIONS_ENABLED=false`; initial bootstrap завершён и **не** повторяется. Реальная Telegram Mini App приёмка текущего нового выпуска назначена на CP-17 после отдельно разрешённого CP-16.

## 5. Финальная проверка и условие CLOSED

После синхронизации **итогового** GitHub HEAD с чистым локальным checkout выполнить один документационный gate:

```bash
python3 ops/tests/test_docs_freshness.py
python3 ops/tests/test_docs_structure.py
python3 ops/tests/test_notification_delivery_contract.py
python3 ops/tests/test_recovery_runbook_contract.py
git diff --check
```

Зафиксировать SHA, фактические результаты, перечень изменённых файлов и обнаруженные противоречия. При необходимости исправить конкретный отказ и повторить профильную проверку. После этого обновить CP-13 evidence в `docs/AUDIT_0_12_REMEDIATION.md`; не переписывать CP-00–14 задним числом. Следующий объём — три прохода CP-15 и согласованные пользователем 12 независимых проверок разделов **после** очистки документов.

**На момент этой записи:** редактирование GitHub не подтверждено локальным выполнением перечисленного gate на новом HEAD; CP-13 остаётся `OPEN`, CP-15 `OPEN`, CP-16/17/18 `OPEN`. Production и миграции не менялись этими документационными коммитами.
