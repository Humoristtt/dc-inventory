# Чистый аудит текущего состояния

Дата: **2026-09-30**  
Аудируемый source baseline: `2ba1fa1b1ca60bbbe4f75bf40e41f826581222c3`  
Alembic source head: `e3f4a5b6c7d8`

Этот документ — результат независимого прохода по текущему репозиторию. Предыдущие audit/remediation/stage документы не использовались как основание для выводов.

## 1. Область аудита

Проверены:

1. структура репозитория и CI;
2. зависимости, supply chain и контейнерные образы;
3. production configuration validation;
4. Telegram authentication, session model, Origin protection и access lifecycle;
5. RBAC/capabilities и административные ограничения;
6. PostgreSQL schema/migrations/readiness/least privilege;
7. Catalog schema, identity и query behavior;
8. Warehouse ledger, stock/custody projections, locks и idempotency;
9. Procurement lifecycle, revisions/events, idempotency и связь со складом;
10. Telegram/email delivery и worker isolation;
11. frontend startup/auth/routing/design-system/runtime hardening;
12. ingress, runtime networks, release provenance, backup/restore и maintenance;
13. документация и её автоматические контракты.

Не выполнялись SSH в production, live Cloudflare changes, Telegram webhook changes, отправка реального email, S3 mutation или production migration. Поэтому audit не выдаёт source evidence за live-production evidence.

## 2. Автоматическое evidence на baseline

GitHub Actions run для audited SHA завершён успешно во всех required jobs:

| Gate | Результат |
|---|---|
| backend | PASS |
| frontend | PASS |
| runtime | PASS |
| telegram-gateway | PASS |

Детали:

- Ruff: PASS;
- mypy: PASS, 212 source files;
- Alembic fresh upgrade: PASS;
- `alembic check`: PASS;
- source Alembic head: `e3f4a5b6c7d8`;
- backend: `648 passed, 1 skipped`;
- frontend unit: `165 passed` в 34 files;
- frontend build/bundle: PASS, initial JS 285273 bytes, gzip 89245 bytes;
- browser acceptance: `142 passed, 12 skipped`;
- production-shaped full-stack: `2 passed`;
- full-stack DB side effects: PASS;
- Telegram Gateway: `7 passed`;
- repository and final image Trivy HIGH/CRITICAL gates: PASS;
- runtime image provenance: PASS;
- runtime DB-role negative privilege checks: PASS;
- maintenance worker boundary: PASS.

## 3. Результат по областям

### 3.1 Authentication / access / RBAC — без найденного blocking defect

Подтверждено по коду и regressions:

- Telegram `initData` проверяется криптографически и ограничен по freshness/размеру;
- серверная сессия хранится по hash token, cookie — HttpOnly;
- state-changing cookie-auth requests проверяют `Origin`;
- `PENDING/APPROVED/REJECTED/BLOCKED` отделены от role;
- backend проверяет capability на endpoint boundary;
- OWNER/recovery identity защищён отдельными правилами;
- role/access mutation сериализуется и пишет immutable audit event;
- блокировка/сброс учётной записи запрещены при несовместимом custody/procurement state.

### 3.2 Database / migrations / invariants — без найденного blocking defect

Подтверждено:

- один Alembic head;
- fresh PostgreSQL 18 migration проходит до head;
- readiness сравнивает DB head с source head;
- readiness проверяет критические triggers/functions/collation;
- inventory/procurement/identity invariants дублируются на PostgreSQL boundary;
- runtime role не владеет схемой и не получает broad DML на immutable/history/projection tables;
- delivery и maintenance workers имеют отдельные DB identities.

### 3.3 Catalog — без найденного correctness defect

Подтверждено:

- фиксированная family/leaf taxonomy;
- typed EAV: TEXT/INTEGER/DECIMAL/BOOLEAN/ENUM;
- required attributes и leaf constraints защищены DB triggers;
- `normalized_name`, `normalized_model`, `identity_signature` защищены DB contract;
- archived item нельзя использовать там, где требуется active identity;
- query/facet path имеет отдельные query-budget regressions.

### 3.4 Warehouse — без найденного correctness defect

Подтверждено:

- Movement/MovementLine — append-only journal;
- stock и custody — DB-derived projections;
- отрицательный stock/custody запрещён;
- idempotency основана на actor + `client_request_id` + request fingerprint;
- lock order явно задан и regression-tested;
- correction/reversal не переписывает историю;
- финальный procurement receipt защищён от generic warehouse adjustment.

### 3.5 Procurement — без найденного blocking defect

Подтверждено:

- mutable request header отделён от immutable revisions/events;
- optimistic state contract: `state_version` + `current_revision_id`;
- action-level idempotency использует `client_request_id` + fingerprint;
- proposed line связывается только с совпадающей Catalog identity;
- quantity агрегируется по итоговому Item;
- final acceptance создаёт Warehouse RECEIPT и переводит request в COMPLETED атомарно.

### 3.6 Notifications — без найденного blocking defect

Подтверждено:

- intent создаётся в PostgreSQL outbox;
- claim использует `FOR UPDATE SKIP LOCKED`, TTL и claim token;
- stale worker не может финализировать чужой claim;
- Telegram Gateway принимает только whitelist методов и ограничивает request body;
- email worker изолирован отдельным DB role и выключен по умолчанию;
- внешняя доставка корректно трактуется как at-least-once.

### 3.7 Runtime / ingress / release / backup — без найденного blocking defect в source

Подтверждено:

- backend/PostgreSQL не публикуют host application ports;
- production ingress override удаляет web TCP publication и использует Unix socket;
- user ingress и Telegram webhook разделены;
- containers используют read-only FS где возможно, `cap_drop: ALL`, `no-new-privileges`, pids/resource limits;
- внешние GitHub Actions и base images pinned;
- release builder требует clean checkout и связывает SHA с immutable image ID;
- backup создаёт custom-format dump, проверяет `pg_restore --list`, SHA-256 и versioned S3 IDs;
- restore rehearsal изолирован от production runtime.

## 4. Найденные текущие проблемы

### F-01 — P2 — нормативная документация была устаревшей и смешивала current state с историей

До этого изменения README и docs содержали старые source/production SHA, прежний Alembic head, CP/Stage/Audit ledgers и прошлые acceptance assertions. При этом `test_docs_freshness.py` мог пройти, потому что сам был привязан к старой структуре и историческим файлам.

**Решение в этом change-set:** исторические audit/stage/history/roadmap документы удалены; текущие документы переписаны от кода; documentation contracts переписаны под current-state модель.

Статус: **CLOSED в данной ветке после зелёного CI**.

### F-02 — P2 — знания о frontend routes дублируются

Текущий frontend хранит route knowledge минимум в четырёх местах:

- JSX `<Route>` в `frontend/src/app/App.tsx`;
- path→loader matcher в `frontend/src/app/routeModules.ts`;
- bottom navigation/active matching в `ApplicationShell.tsx`;
- default/back behavior в `useTelegramNavigation.ts`.

Это не текущий функциональный сбой, но изменение маршрута может рассинхронизировать render/preload/navigation/back behavior.

Статус: **OPEN, maintainability**.

### F-03 — P3 — крупные frontend orchestration components

Текущие размеры:

- `ItemFormPage.tsx`: 958 строк, основной component — около 745;
- `AdminUsersPage.tsx`: 850, component — около 726;
- `ProcurementDetailPage.tsx`: 754, component — около 561;
- `LineComposer.tsx`: 679, component — около 548;
- `MovementsPage.tsx`: 549, component — около 521;
- `CategoryPage.tsx`: 540, component — около 483.

Функции покрыты тестами, но server state, form state, mutation orchestration и presentation слишком тесно связаны.

Статус: **OPEN, maintainability**. Декомпозиция должна быть behavior-preserving и выполняться отдельными малыми change-set.

### F-04 — P3 — крупные backend service modules

Текущие размеры:

- `procurement/service.py`: 1472 строки;
- `catalog/query.py`: 1403;
- `catalog/service.py`: 1080;
- `inventory/service.py`: 987;
- `_create_movement()`: около 332 строк;
- `complete_acceptance()`: около 156;
- `build_catalog_query_spec()`: около 161.

Correctness contracts сильные, но стоимость безопасного изменения растёт.

Статус: **OPEN, maintainability**. Разделять только по существующим transaction/lock boundaries, не меняя lock order и transaction ownership.

### F-05 — P3 — npm сообщает один high-severity advisory во время `npm ci`

В successful frontend/runtime jobs npm печатает `1 high severity vulnerability`. Одновременно обязательный Trivy filesystem scan и финальные image scans HIGH/CRITICAL проходят.

Это означает не подтверждённую runtime-уязвимость, а **неразрешённый dependency-audit signal**: из текущего CI log нельзя установить пакет/advisory и runtime reachability.

Статус: **OPEN**. Следующий безопасный шаг — получить `npm audit --json` на текущем lockfile, определить dependency path и только после этого обновлять пакет/lockfile. Не использовать `npm audit fix --force` без анализа.

## 5. Итог

На audited baseline не найдено P0/P1 correctness/security defect, который по имеющимся source+CI evidence делает систему заведомо небезопасной или неконсистентной.

Открыты:

- 1 P2 maintainability finding по route metadata;
- 2 P3 maintainability findings по размеру frontend/backend orchestration;
- 1 P3 dependency-audit finding.

Отдельно остаётся **неизмеренное live production state**. Это не finding исходного кода: его нельзя достоверно вывести из Git. Перед production change необходимо выполнить runtime verification из `OPERATIONS.md`.

## 6. Правило дальнейшей работы

Этот аудит — единственный audit-документ. Новые замечания добавляются сюда как current findings с evidence и статусом. Для каждого исправления достаточно:

```text
finding → root cause → минимальный change-set → focused regression → затронутый full gate
```

Отдельные remediation plans, stage ledgers и длинные исторические journals не создаются.
