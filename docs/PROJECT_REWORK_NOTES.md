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
Статус: IN PROGRESS

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

### Подтверждённые текущим кодом

- [OPEN] HIGH backend/config — production validation проверяет наличие основных Telegram secrets, но не отвергает semantic placeholders вроде `replace-with-*`. `ops/validate_env_file.py` вообще проверяет только имена ключей. Решение: единый production-secret validator + tests на placeholder/default/blank/whitespace.
- [OPEN] MEDIUM backend/auth — `get_authenticated_context()` может менять recovery OWNER и делать `db.commit()` внутри dependency даже на обычном GET. Это скрытая write-side-effect в authentication layer. Решение: вынести reconciliation в явный startup/admin/recovery path либо строго документировать и тестировать mutation semantics.
- [OPEN] MEDIUM backend/architecture — `identity/reset_service.py` импортирует приватный `_lock_actor_and_target` из `admin_service.py`; аналогично другие модули используют приватные helpers соседних API/service modules. Решение: публичные policy/locking adapters с явными контрактами.
- [MEASURE] MEDIUM auth/security — signed Telegram initData имеет HMAC + TTL + future-skew, но нет one-time/replay state. Не внедрять произвольный nonce store до определения launch/retry policy; сначала threat model и compatibility tests.
- [OPEN] HIGH procurement/api — `_raise_db_error()` превращает любой не-retryable `DBAPIError` в HTTP 409. Infrastructure/internal SQLSTATE не должны маскироваться как business conflict. Решение: общий DB error classifier и negative matrix.
- [OPEN] HIGH procurement/idempotency — mutation replay scope = `request_id + actor_user_id + client_request_id`; action identity отсутствует. Один ключ может replay-нуть результат другого действия при совпавшем fingerprint. Решение: action-scoped idempotency contract + DB uniqueness + regressions.
- [OPEN] HIGH procurement/quantity — aggregate quantity одного Item валидируется только при финальной acceptance; невалидная заявка может пройти почти весь workflow. Решение: общий aggregate guard на create/revision/bind paths и финальный defense-in-depth.
- [OPEN] HIGH procurement/email — email dedupe key включает request/actor/client key, но не recipients/content. Повтор с тем же key и другим `to/cc` может вернуть старый outbox row. Решение: payload fingerprint/conflict semantics.
- [OPEN] MEDIUM telegram — обработка message text вызывает `text.split(maxsplit=1)[0]`; whitespace-only строка даёт пустой список и может упасть. Решение: strip/guard + regression.
- [OPEN] MEDIUM catalog — speed sorting извлекает произвольную цифру из text и cast-ит в `Numeric(20,6)`; очень длинное число может дать DB overflow. Решение: bounded parse/cast или CASE guard + PG regression.
- [OPEN] HIGH frontend/procurement — action buttons не имеют общего pending guard; `expectedState()` создаёт новый UUID на каждый вызов. Быстрый double-click отправляет две независимые mutation-команды. Решение: single-flight UI intent + disabled/locked dialogs + test.
- [OPEN] MEDIUM frontend/procurement — managers/locations/binding item queries не имеют единообразных explicit error/retry states; часть failures выглядит как empty dataset. Решение: общий query-state UI primitive.
- [OPEN] MEDIUM frontend/architecture — крупные компоненты `ItemFormPage.tsx`, `AdminUsersPage.tsx`, `ProcurementDetailPage.tsx`, `LineComposer.tsx` смешивают data loading, mutation orchestration и presentation. Рефакторить только после behavioral regression.
- [OPEN] MEDIUM catalog/performance — полный facets path делает фиксированные base queries + отдельный query на каждый filterable attribute. Нужен batched facet execution и real-PG query budget.
- [OPEN] HIGH deploy/config — Compose строит PostgreSQL URI прямой подстановкой password; reserved URI characters меняют parsing. Решение: отдельные connection fields / encoded URL construction, плюс round-trip tests.
- [OPEN] HIGH release — filesystem release publication атомарна, но partial Docker build может оставить revision tags; retry того же SHA затем блокируется. Решение: verified resume либо безопасный cleanup/transactional tag strategy.
- [OPEN] MEDIUM deploy/docs — recovery OWNER one-shot command остаётся интерактивным по stdin. Решение: non-interactive/no-tty/stdin closed contract и test.
- [OPEN] MEDIUM CI/security — generic action-pin parser покрывает только `- uses:`; named-step `uses:` сейчас pinned, но generic guard их не видит. Решение: YAML-aware scan или regex для обеих форм.
- [OPEN] HIGH CI/fullstack — mutating full-stack scenario существует, но skipped без `FULLSTACK_MUTATIONS_ENABLED=true`; required CI этот flag не задаёт и затем ожидает нулевые warehouse rows. Реальный mutation path не является required gate.
- [OPEN] HIGH backup — backup state не имеет signal-safe `TERM/INT` lifecycle и отдельного `running` state; старый success может пережить принудительное завершение до age alarm.
- [OPEN] HIGH backup — runtime provenance/Alembic фиксируются до `pg_dump`, но после dump не перепроверяются и не координируются с deploy/migration. Возможен inconsistent manifest при overlap.
- [OPEN] HIGH restore — rehearsal восстанавливает и запускает backend под privileged `dc_inventory_restore`; штатный least-privilege role bootstrap/deny matrix не доказывается.
- [OPEN] MEDIUM restore — exact S3 VersionId уже используется, но recovery-point pointer зависит от локального `last-success.json`; при потере VM нет независимого каталога выбранной версии.
- [OPEN] MEDIUM restore — нет обязательного recovery-point age/RPO acknowledgement и нет durable sanitized evidence artifact, сохраняемого после cleanup.
- [OPEN] MEDIUM test architecture — часть контрактов проверяет строки/форму исходника вместо поведения; отдельно требуется real-PG SQL capture/query budget, negative matrices и executable restore/release tests.
- [OPEN] MEDIUM documentation — текущая документация раздроблена на 24 Markdown-файла, содержит дубли current-state, старые SHA/checkpoint/status и несколько исторических планов. После стабилизации source оставить только канонические документы и перенести уникальную историю в один history/changelog.

### Style / consistency

- [OPEN] LOW code-style — backend comments/docstrings смешивают русский и английский; архитектурные термины и error messages тоже не имеют единого правила. Предлагаемый стандарт: code identifiers/comments/docstrings — English; user-facing UI/errors/docs — Russian, кроме устойчивых технических терминов.
- [OPEN] LOW architecture — встречаются private imports между sibling modules и локальные imports для обхода связности. Перед рефакторингом построить import/dependency map и убрать только реальные boundary violations, не исторические migrations/vendor.
- [OPEN] LOW docs-style — current-state facts, runbook commands, history и implementation notes смешаны в одних файлах. Разнести ответственность документов после source stabilization.

Заполняется только по текущему коду; каждый пункт перед исправлением получает точный regression/acceptance contract.

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
