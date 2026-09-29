# PROJECT REWORK NOTES

> Временный рабочий журнал полной ревизии проекта. Перед финальным merge этот файл должен быть либо удалён, либо преобразован в короткий changelog. Он не является пользовательской документацией.

## Baseline

- Source branch: `refactor/full-project-review-20260929`
- Base: `main=60c5a88d11f46484996fd784d45c3b40bd070cfb`
- Production в рамках этой работы не изменяется до отдельного release/cutover этапа.

## Цель

Пройти проект целиком по текущему коду, независимо от исторических отчётов, и привести его к единому состоянию:

1. correctness и целостность данных;
2. security и least privilege;
3. concurrency/idempotency;
4. единые архитектурные границы;
5. единый стиль backend/frontend/ops;
6. тесты, которые проверяют поведение, а не строки исходника;
7. CI/release/backup/recovery, соответствующие реальному runtime;
8. документация, описывающая только текущее состояние;
9. удаление устаревших, дублирующих и исторических документов после стабилизации кода.

## Правило работы

- Сначала фиксируем факт и место проблемы в этом журнале.
- Не переписываем крупный модуль до фиксации его поведения regression-тестами.
- Не смешиваем functional fix и косметический refactor, если это увеличивает blast radius.
- DB/security/recovery изменения получают отдельные negative tests.
- Production не меняется в ходе source cleanup.
- После каждого логического пакета — CI.
- После стабилизации кода документация переписывается по факту source/runtime, затем исторический мусор удаляется.

## Карта полного прохода

### 1. Backend core / auth / identity
Статус: TODO

Проверить:
- конфигурацию и fail-closed production validation;
- session/origin/Telegram auth;
- RBAC/capability policy;
- error mapping;
- shared utilities и дублирование;
- транзакционные границы и lock order;
- фоновые workers.

### 2. Catalog
Статус: TODO

Проверить:
- query parser/search/sort/facets;
- EAV validation;
- manufacturer/model policy;
- pagination/query budgets;
- oversized numeric/text inputs;
- API/service layering.

### 3. Inventory / warehouse
Статус: TODO

Проверить:
- immutable journal;
- projections;
- movement transaction;
- custody;
- correction/reversal;
- history/feed;
- deprecated routes;
- SQL privileges.

### 4. Procurement
Статус: TODO

Проверить:
- state machine;
- revisions/events;
- idempotency;
- aggregate quantities;
- email;
- binding/acceptance;
- DB error classification;
- cross-action behavior.

### 5. Frontend
Статус: TODO

Проверить:
- query/error/loading/empty states;
- mutation double-submit;
- shared constants/contracts;
- oversized components;
- API client consistency;
- accessibility/mobile;
- cache invalidation;
- page/query pagination.

### 6. PostgreSQL schema / migrations / permissions
Статус: TODO

Проверить:
- constraints/FK/unique/indexes;
- historical migration safety;
- role grants;
- SECURITY DEFINER functions;
- schema readiness contract;
- downgrade/upgrade behavior.

### 7. CI / test architecture
Статус: TODO

Проверить:
- required workflows;
- skipped real scenarios;
- source-text tests vs behavioral tests;
- action pinning;
- PostgreSQL integration coverage;
- browser/full-stack path;
- restore/release contracts.

### 8. Docker / release / deploy
Статус: TODO

Проверить:
- env/URL construction;
- immutable tags and interrupted build;
- runtime isolation;
- secret propagation;
- health/readiness;
- one-shot CLI non-interactive behavior.

### 9. Backup / restore / DR
Статус: TODO

Проверить:
- signal-safe state;
- provenance before/after dump;
- object version identity;
- recovery-point catalog;
- least-privilege role bootstrap;
- RPO/age acknowledgement;
- durable evidence;
- cleanup ownership/concurrency.

### 10. Cloudflare / Telegram gateway
Статус: TODO

Проверить:
- request validation;
- secret handling;
- retry/dedupe;
- status/error handling;
- test coverage;
- consistency with backend webhook contract.

### 11. Documentation
Статус: DEFERRED UNTIL SOURCE STABLE

Нужно:
- оставить минимальный набор актуальных документов;
- переписать README/navigation/architecture/operations/deployment/recovery;
- объединить дубли;
- удалить исторические remediation/stage/checkpoint документы и старые планы;
- убрать SHA/status, которые быстро протухают, если они не нужны как release evidence;
- все команды должны быть copy-paste safe и соответствовать текущему runtime.

## Findings ledger

Формат:
`[OPEN|FIXED|WONTFIX|MEASURE] [severity] subsystem — факт → причина → решение → regression`

Пока пусто. Заполняется только по текущему коду.

## Final gates

Перед завершением:
- backend lint/typecheck/tests PASS;
- real PostgreSQL integration PASS;
- frontend lint/typecheck/unit/build/browser PASS;
- mutating full-stack PASS на disposable DB;
- release failure/retry PASS;
- restore rehearsal PASS с production-like roles;
- docs contracts PASS;
- `git diff --check`;
- независимый финальный source review без ссылок на исторические отчёты;
- затем отдельное решение о production rollout.
