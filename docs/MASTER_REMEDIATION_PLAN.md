# MASTER REMEDIATION — CP-18 post-audit

**Дата сверки:** 25.09.2026.  
**Рабочая ветка:** `remediation/cp18-findings-20260925`.  
**Base:** `main=3de3d0f57a2b8a751df81f6970f81a9e25ded16d`, tree `493fe8ea44dc2e049b948f41d93a8924620aa160`.  
**Последний принятый production runtime:** `593ddec0c9100b0df2eafe4f324c7bb600d75cba`, Alembic `b0c1d2e3f4a5`, evidence 25.09.2026.

Этот файл — выполняемый план после независимого CP-18 Audit 0–12. Исходный PDF остаётся историческим источником первоначальных ID. В CP-18 подтверждено **54 активных ID**, но это не 54 независимых root cause: связанные test-gap, documentation и maintainability ID исправляются вместе с основной причиной.

## 1. Границы работ

В рамках remediation разрешены изменения Git/source/tests/docs в отдельной ветке. Production, S3, Cloudflare, Telegram webhook, реальные секреты и safety flags не меняются без отдельного production change.

`REAL_INVENTORY_MUTATIONS_ENABLED=false` и `EMAIL_DELIVERY_ENABLED=false` остаются последним подтверждённым production baseline. Никакой DDL на production до отдельного preflight, backup, compatibility и cutover plan.

Статус CP-18:

```text
AUDIT_0_12=COMPLETE
ACTIVE_FINDING_IDS=54
NEW_A12_FINDINGS=0
FINAL_PROJECT_ACCEPTANCE=NOT_PASSED
```

Живой старый P1 Telegram ADMIN→ADMIN bypass устранён. Остаётся high-priority parity test gap `A6-P1-001`, но он не является подтверждённым действующим bypass.

## 2. Правило закрытия

ID закрывается только когда одновременно выполнены: исходный сценарий воспроизведён или его механизм однозначно доказан; исправлена корневая причина; добавлен отрицательный regression; положительные regression проходят; required CI включает соответствующий gate; связанные current-state docs не обещают более сильную гарантию, чем код/тест; для production-dependent пункта отдельно получено production evidence.

Связанные ID не получают отдельные дублирующие реализации. Один root cause — один change-set, один набор regression и один acceptance result.

## 3. Приоритет и пакеты исправлений

| Порядок | Пакет | Основные ID | Выход |
|---|---|---|---|
| 1 | **DB delivery least-privilege** | `A4-P2-002`, `A6-P2-002`, часть `A10-P3-006`, X12-02 | Telegram worker: column-scoped UPDATE; CI проверяет разрешённые/запрещённые колонки; docs соответствуют фактическим grants. |
| 2 | **PostgreSQL invariants** | `A2-P2-001/002/003/004/005/008`, `A6-P2-006`, X12-05/06 | Новая migration/guards + real-PG negative regressions: completed unlink, typed EAV, event states, projection boundary, event↔revision ownership, historical b3 drift protection. |
| 3 | **Procurement/idempotency correctness** | `A1-P2-001/002`, `A1-P3-004/005`, `A3-P2-001/002`, `A6-P2-003/004/008`, `A11-P3-005`, X12-04 | DB error mapping, email payload-aware idempotency, empty Telegram text, safe numeric sort, aggregate quantity validation, action-scoped replay policy and regressions. |
| 4 | **Frontend failure safety** | `A5-P2-003`, `A5-P3-006`, остаток `A6-P2-007`, `A11-P2-004`, `A11-P3-007` | At-most-one UI mutation while pending, explicit lookup error/retry, regressions; затем аккуратный ItemForm decomposition без смены поведения. |
| 5 | **Required CI coverage** | `A0-P2-003`, `A0-P3-004`, `A6-P1-001`, `A6-P2-005`, `A6-P3-009`, X12-08/14 | repository-data-policy и frozen-migration contracts в required CI; RBAC negative parity; mutating full-stack реально запускается; DR gate усилен. |
| 6 | **Release/config safety** | `A4-P2-003`, `A8-P2-001/002`, `A8-P3-003/004`, `A10-P3-007` | Reject placeholder secrets; безопасные DB credentials/URL; interrupted build recovery; noninteractive OWNER CLI; корректный parser GitHub Action refs. |
| 7 | **Backup/restore/DR** | `A9-P2-001/003/004/005`, `A9-P3-006/007`, `A6-P3-009`, `A10-P2-003`, X12-10/11 | Off-VM recovery-point pointer, signal-safe state, pre/post provenance, role bootstrap/deny checks, RPO consent и durable evidence. |
| 8 | **Query scalability** | `A7-P2-002`, `A6-P3-010`, `A11-P2-003`, плюс `A1-P3-005` после correctness | Убрать facet `3+N`; real-PG query budget/EXPLAIN regression; разделить query parser/predicates/facets после сохранения семантики. |
| 9 | **Maintainability после функциональных fixes** | `A11-P2-001/002`, `A11-P3-006/008` и оставшиеся A11 | Декомпозиция только после зелёных DB/domain regression, без изменения lock order, transaction ownership и API contracts. |
| 10 | **Current-state docs + final cleanup** | `A0-P2-001`, `A10-P2-003/004/005`, остаток `A10-P3-006` и CP-18 ledger | Развести source/main и production baseline; убрать ложные acceptance assertions; после финального re-audit консолидировать Markdown. |

Условные исследования `A4-P3-004` (initData anti-replay) и `A7-P3-003` (worker concurrency) не превращать в кодовый fix без принятого threat model/SLO и измерений.

## 4. Зависимости

1. Security/DB correctness идут раньше refactor.
2. PostgreSQL invariants — раньше декомпозиции `inventory/service.py` и междоменных boundary.
3. Procurement action-scoped idempotency — раньше выноса shared fingerprint/advisory primitives.
4. Frontend behavior regressions — раньше декомпозиции ItemForm.
5. DR script fixes — раньше переписывания recovery docs.
6. Документация о текущем состоянии обновляется после соответствующего source/test change, но очевидно ложный `main` baseline исправляется в этом remediation cycle.
7. Production deployment — только после отдельного release gate; текущая ветка production не меняет.

## 5. Acceptance для каждого пакета

Минимальный gate каждого change-set:

- targeted unit/static tests;
- real PostgreSQL regression, если затронуты schema/grants/locking;
- Ruff + mypy для backend changes;
- frontend unit/typecheck/lint/build для frontend changes;
- профильные ops contracts;
- required GitHub CI на PR;
- `git diff --check`;
- отсутствие секретов/private inventory в diff.

После всех пакетов: новый independent Audit 0–12 на финальном SHA. Только затем production release decision и финальная Markdown-консолидация.

## 6. Первый выполняемый change-set

Начинаем с **DB delivery least-privilege**, потому что пакет мал по blast radius, не требует DDL и одновременно закрывает реальную security boundary и неверный CI oracle:

- заменить table-wide Telegram worker `UPDATE notification_outbox` на разрешённые delivery-state колонки;
- оставить payload/method/dedupe/id/created_at недоступными для UPDATE;
- изменить CI с `has_table_privilege(..., 'SELECT, UPDATE')` на table SELECT + exact column UPDATE matrix + отрицательные checks;
- усилить `test_runtime_database_role_contract.py`;
- синхронизировать OPERATIONS после фактического source fix;
- затем дождаться required CI и только после PASS переходить к PostgreSQL invariants.

## 7. Текущее состояние выполнения

```text
CP18_AUDIT_0_12=COMPLETE
REMEDIATION_BRANCH=remediation/cp18-findings-20260925
PACKAGE_01_DB_DELIVERY_LEAST_PRIVILEGE=IN_PROGRESS
PRODUCTION_CHANGED=NO
```
