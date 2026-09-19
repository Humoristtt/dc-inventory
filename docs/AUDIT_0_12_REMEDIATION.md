# Audit 0–12 remediation ledger

This document is the repository-local execution ledger for the post-RBAC
Audit 0–12 remediation program.

The definitive source findings are tracked from the accepted master remediation
ledger. Exact standalone Audit 1 / Audit 2 source reports are not available;
the master ledger is explicitly accepted as the remediation source of truth.

## Global state

- Project remediation status: `OPEN`
- Remediation branch: `remediation/audit-0-12`
- Original source baseline:
  `22ca1fdb9b4ab2ab813fba2ca531ca90d248cf35`
- Original Alembic head: `d4e5f6a7b8c9`
- Production changed by remediation work: `NO`
- `REAL_INVENTORY_MUTATIONS_ENABLED=false`
- `EMAIL_DELIVERY_ENABLED=false`

No production deployment is permitted before the dedicated deployment
checkpoints.

## Finding state rules

Allowed states:

- `OPEN`
- `IN_PROGRESS`
- `CLOSED`
- `SUPERSEDED`
- `ACCEPTED_RISK`
- `NOT_REPRODUCIBLE`

A database-invariant finding is not closed by an application-service-only fix.
A regression is not closed without reproducing the original failure and proving
the corrected behavior.

## Checkpoints

### CP-00 — Baseline / source ledger

Status: `PASS`

Evidence:

- source baseline and clean-worktree checks accepted;
- master remediation ledger accepted as source of truth;
- historical Audit 1 / Audit 2 source-report gap explicitly accepted;
- production unchanged.

Checkpoint commit: none; baseline-control checkpoint.

### CP-01 — P1 regression capture

Status: `PASS`

Commit:

`8546ec6be8765415fe9d58e45f500d22fbe1f8b4`

Evidence:

- 9 expected-red backend regressions;
- 1 expected-red frontend idempotency regression;
- 1 expected-red restore/session regression;
- total: 11 reproduced scenarios.

This checkpoint records failures; it does not close the findings.

### CP-02 — Database invariant foundation

Status: `CLOSED`

#### CP-02.1 — Procurement database invariants

Status: `PASS`

Commit:

`55700aff0c1fbb0690bac254e77c12e97214cf8d`

Closed technical gaps:

- committed Procurement revision rejects late line INSERT;
- an already corrected/reversed Warehouse movement cannot later become
  `final_movement_id`;
- reverse movement/final-binding race is serialized at the database boundary.

Migration:

`e5f6a7b8c9d0`

#### CP-02.2 — Identity / RBAC database invariants

Status: `PASS`

RED checkpoint:

`426acc53d4ca8fd0ab3bfe5a7b6ca194a2911113`

Implementation checkpoint:

`d3675b6c835f201b4e5e723d3f564fb4135701a9`

Closed technical gaps:

- OWNER must remain APPROVED at the database boundary;
- `users.access_status` mutation requires same-transaction immutable audit;
- `users.role` mutation requires same-transaction immutable audit.

Migration:

`f6a7b8c9d0e1`

#### CP-02.3 — Catalog required attributes / custody / schema readiness

Status: `PASS`

RED checkpoint:

`86c5420e21fcb491f0de1dc6fe8746456fe55f83`

Implementation checkpoint:

`6aa45ce7b8c541b1e7bd0a249f3e2b84139a4fd1`

Closed technical gaps:

- required Catalog EAV attributes are a database invariant;
- custody projection holder eligibility is enforced in both directions;
- critical PostgreSQL trigger/function contract is part of readiness;
- migration downgrade/upgrade and post-roundtrip readiness pass.

Migration:

`f7a8b9c0d1e2`

#### CP-02.4 — Catalog derived identity integrity

Status: `PASS`

RED checkpoint:

`585262281875df8448fa132bb99426ac2bcba196`

Implementation checkpoint:

`562a69e6f88a464c56542c4c4b132ba7fcaa37b0`

Closed technical gaps:

- `normalized_name` cannot diverge from canonical `name`;
- `normalized_model` cannot diverge from canonical `model`;
- `identity_signature` cannot diverge from canonical Item/EAV data;
- Python and PostgreSQL use equivalent full Unicode case folding;
- decimal identity representation is exact and context-independent;
- critical Catalog identity functions, triggers and collation are covered
  by database readiness.

Migration:

`f8b9c0d1e2f3`

Evidence:

- 12 CP-02.4 target/compatibility tests pass;
- existing Catalog / CP-02.3 / health compatibility suite passes;
- identity drift reconciliation returns zero rows;
- migration downgrade/upgrade roundtrip passes;
- post-roundtrip readiness passes.

#### CP-02 consolidated closure

Status: `PASS`

Migration-contract compatibility checkpoint:

`c4525df3be9c9a81d1240fc4886bc6f4fe81656d`

Runtime least-privilege checkpoint:

`a9fe1e512324718a8dbeaf8db30eb32af10193ff`

Consolidated evidence:

- fresh PostgreSQL database migrates from zero to the single Alembic head
  `f8b9c0d1e2f3`;
- fresh-database OWNER, required Catalog attribute, custody and derived Catalog
  identity invariants report zero violations;
- full backend regression passes with `509 passed, 1 skipped`;
- explicit CP-02 database-contract suite passes with `52 passed`;
- migration head remains `f8b9c0d1e2f3` after the full suite;
- effective test safety gates keep real inventory mutations and email delivery
  disabled;
- the runtime database principal no longer has table-wide UPDATE on
  `users`, `telegram_identities` or `access_requests`;
- required identity/access mutation columns remain writable while immutable
  `users.created_at`, `telegram_identities.telegram_user_id` and
  `access_requests.requested_at` are denied to the runtime role;
- runtime-role attack regression passes against the real permission contract;
- final gate leaves the repository clean and does not change production.

### CP-03 — RBAC cross-channel

Status: `CLOSED`

RED checkpoint:

`ccc02dccc985bb156fed5ebc170d46469304821e`

Test-isolation checkpoint:

`35d6477e91c45f3e4c4ad5a0499e15deff0cf13a`

Implementation checkpoint:

`3b0fd7cf0a70d5a8eaa3fd3a7ed020e849571270`

Closed technical gaps:

- Web and Telegram access decisions use the same target-aware authorization primitive;
- ADMIN-target access decisions require OWNER capability on both channels;
- privileged Telegram access callbacks expire after the configured TTL;
- Telegram no longer owns a separate direct access-state transition path;
- access audit semantics remain coupled to the shared identity lifecycle;
- Telegram delivery PostgreSQL tests preserve User/TelegramIdentity consistency
  across repeated runs.

Evidence:

- CP-03 target / cross-channel PostgreSQL suite: `74 passed`;
- configuration contract suite: `40 passed`;
- backend regression excluding separately tracked CP-01 Procurement RED:
  `512 passed, 1 skipped`;
- migration head remained `f8b9c0d1e2f3`;
- frontend RBAC suite: `25 passed`;
- frontend regression excluding the separately tracked CP-05
  `ProcurementCreatePage.cp01.test.tsx`: `139 passed`;
- frontend typecheck, lint and production build pass;
- fresh PostgreSQL migration from zero to `f8b9c0d1e2f3` passes;
- repository was clean after the implementation checkpoint;
- production was not changed.

Deferred dependency:

- the Procurement lost-response `client_request_id` regression remains RED and
  is intentionally deferred to CP-05 / `R-PROC-IDEMP`.

Exit marker:

`CP-03_RBAC_CHANNEL_PARITY=PASS`

### CP-04 — Procurement semantic identity / lifecycle

Status: `CLOSED`

Exit marker: `CP-04_PROCUREMENT_INTEGRITY=PASS`

Evidence:
- implementation commits: `bd7603c`, `bdb719d`;
- migration metadata commit: `6821f85`;
- historical migration RED: `8e06ed7`;
- historical snapshot migration fix: `0ca4292`;
- Alembic head: `a9c0d1e2f3a4`;
- approved historical Procurement identity is reconstructed from immutable
  `display_snapshot`, not current Catalog Item or binding state;
- unresolved historical identity reconstruction fails closed;
- historical populated migration regression: `1 passed`;
- migration regression: `15 passed`;
- zero-to-head / Alembic check: PASS;
- Procurement append-only trigger after migration: PASS;
- consolidated full backend: `527 passed, 1 skipped`;
- consolidated full frontend: `147 passed`;
- frontend typecheck / lint / build / bundle contract: PASS;
- production changed: NO.

### CP-05 — Procurement UI correctness

Status: `CLOSED`

Exit marker: `CP-05_PROCUREMENT_UI_CORRECTNESS=PASS`

Evidence:
- idempotency / queue pagination RED: `ef0c764`;
- stable logical retry and queue pagination implementation: `1b00ae5`;
- lookup / picker RED: `fad61c6`;
- searchable and paginated lookup / picker implementation: `5f4fdd9`;
- lost-response retry preserves one stable `client_request_id`;
- Procurement queues are paginated beyond the initial 30 rows;
- manager and manufacturer lookups are searchable and paginated;
- Catalog and binding pickers load beyond their initial page;
- stale Catalog selection is cleared when search context changes;
- focused Procurement frontend contracts: `18 passed`;
- consolidated full frontend: `147 passed`;
- consolidated full backend: `527 passed, 1 skipped`;
- frontend typecheck / lint / build / bundle contract: PASS;
- production changed: NO.

### CP-06 — Performance

Status: `CLOSED`

#### CP-06.1 — Procurement query scalability

Status: `CLOSED`.

Implementation: `be97d3f8c2f98b0106161cab294b75bcd759eb91`.
Acceptance tests: `dbea4953f2d0c77d57079e19a7485134b11c06f1`.

Verified:
- Procurement summary: 3 SELECT, no history-table reads.
- Existing items: 2 SELECT for 1/100/500 distinct Item IDs.
- Mixed proposed items: 3 SELECT for 1/100/500 lines.
- Views `my`, `active`, `history`: filtering, ordering, pagination,
  serialization and revision metadata verified.
- Negative cases: missing/archived items, invalid attributes and
  error precedence verified.
- CP-06 tests: 11 passed.
- Focused regression: 56 passed.
- Full backend: 538 passed, 1 skipped.
- Zero-to-head PostgreSQL migration: PASS.
- Ruff and diff checks: PASS.
- Disposable database removed; production unchanged.

#### CP-06.2 — Catalog stock, facets and pagination

Status: `CLOSED`.

Acceptance tests: `3718f64aa267788125e4523dae7285663a979182`.

Verified for `optical_patch_cord` on a disposable PostgreSQL database:
- Catalog list: 3 SELECT for 1, 100 and 500 matching items.
- Full facets: 10 SELECT for 1, 100 and 500 matching items.
- Single availability facet: 1 SELECT.
- Stock quantities, IN_STOCK filtering, deterministic pagination,
  facet value pagination and counts verified.
- Diagnostic observation for 500 items: 66.1 ms total facet processing;
  42.5 ms measured around SQL driver calls in one run. This is not
  a production performance guarantee.
- Focused Catalog regression: 23 passed.
- Full backend: 539 passed, 1 skipped.
- Zero-to-head PostgreSQL migration and Ruff checks: PASS.
- Disposable database removed; production code unchanged.

The original six-SELECT target was provisional and not supported
by a measured performance requirement. The accepted query-count
contract is specific to this category and its current facet schema.
Further optimization requires production-representative measurements.

### CP-07 — Frontend architecture / HTTP hardening

Status: `OPEN`

Frontend:
- Исправления сохранены в коммите `d22301cc3fb08a3a6e1bffaff2ac31b9cac178e2`.
- Локальные проверки frontend завершены: 148 тестов, lint, typecheck и build — PASS.

HTTP:
- Реализованы отдельные TCP- и Unix-входы Nginx.
- TCP не доверяет `CF-Connecting-IP` и входящему `X-Forwarded-Proto`.
- Unix-вход использует `real_ip_header CF-Connecting-IP` и `set_real_ip_from unix:`.
- Локальная сборка и `nginx -t` — PASS.
- TCP: смена заявленного IP не обходит rate limit — PASS.
- Unix: лимит одного клиента и изоляция второго клиента — PASS.
- Передача нормализованных IP и схемы в backend — PASS.
- Доступ к сокету: посторонний пользователь отклонён, разрешённая группа допущена — PASS.

Ограничения:
- Первоначальный тест выявил доступность сокета `0666` через каталог `0755`.
- Защита проверена после установки прав каталога `0750`.
- Фактические UID/GID, права bind mount и доступ пользователя `cloudflared` на production не проверены.
- Production по-прежнему использует Tunnel origin `http://localhost:8080`.
- Новый web-образ нельзя разворачивать с прежним TCP-маршрутом Tunnel: публичные клиенты могут разделить один rate-limit bucket.

Локальная реализация проверена. Production migration остаётся OPEN.
Процедура и результаты: `docs/CP07_HTTP_SOCKET_MIGRATION.md`.

### CP-08 — Async outbox / email / Telegram launch

Status: `OPEN`

### CP-09 — DB permissions / operational transaction safety

Status: `OPEN`

### CP-10 — Release / deploy / artifact integrity

Status: `OPEN`

### CP-11 — Backup / restore / DR

Status: `OPEN`

### CP-12 — Maintainability

Status: `OPEN`

### CP-13 — Documentation

Status: `OPEN`

### CP-14 — Real isolated full-stack acceptance

Status: `OPEN`

### CP-15 — Three-pass pre-deployment audit

Status: `OPEN`

### CP-16 — Controlled production deployment

Status: `OPEN`

### CP-17 — Real Telegram Mini App acceptance

Status: `OPEN`

Manual acceptance must use the real Telegram Mini App after deployment.

### CP-18 — Fresh independent Audit 0–12

Status: `OPEN`

This is a fresh independent audit after all remediation and acceptance work.

## Current next action

Execute CP-06 — Performance remediation.

CP-04 Procurement integrity and CP-05 Procurement UI correctness are closed.
Next work must begin from the CP-06 performance scope without modifying the
closed CP-04 / CP-05 contracts unless a new regression is independently proven.

---

## Checkpoint journal — CP-04 Procurement integrity

CHECKPOINT_ID=CP-04
DATE=2026-09-16
BASELINE_BEFORE=77ad901092f638b9a9ef04bfc7e801a9bd1bcb60
IMPLEMENTATION_HEAD=6821f8537b7070e9daa5cf5f0aa12f5e8b98352f

RED_CHECKPOINT=fa78cd249cebceaae372c7f50f528cd5fe7028ae
IDENTITY_IMPLEMENTATION=bd7603c82244ef19fddb77031584bafdbffbd8a7
AUTHORIZATION_IMPLEMENTATION=bdb719d6b27e7c49f8ed5be6d2886f3fc2a85898
MIGRATION_TEST_METADATA=6821f8537b7070e9daa5cf5f0aa12f5e8b98352f

MIGRATION_HEAD=a9c0d1e2f3a4
MIGRATION_ZERO_TO_HEAD=PASS
MIGRATION_ROUNDTRIP=PASS
PROCUREMENT_APPEND_ONLY=PASS
CP04_CONTRACT_SET=PASS
FULL_BACKEND_REGRESSION=PASS
BACKEND_RESULT=524 passed, 1 skipped
FRONTEND_NON_CP05_BASELINE=PASS
FRONTEND_RESULT=139 passed
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_BUILD=PASS
CP05_KNOWN_RED_PRESERVED=PASS

REAL_INVENTORY_MUTATIONS_ENABLED=false
EMAIL_DELIVERY_ENABLED=false
PRODUCTION_CHANGED=NO

STATUS=PASS
NEXT_CHECKPOINT=CP-05_PROCUREMENT_UI_CORRECTNESS

CP-04_PROCUREMENT_INTEGRITY=PASS

---

## Checkpoint journal — CP-04 historical migration addendum

CHECKPOINT_ID=CP-04.3
DATE=2026-09-16
BASELINE_BEFORE=0ca4292879100489994403584b63f6521f7f8e66

HISTORICAL_MIGRATION_RED=8e06ed74c7c74b593c9e58edbafba02b788db2e6
HISTORICAL_MIGRATION_FIX=0ca4292879100489994403584b63f6521f7f8e66

MIGRATION_HEAD=a9c0d1e2f3a4
HISTORICAL_POPULATED_MIGRATION=PASS
HISTORICAL_MIGRATION_RESULT=1 passed
MIGRATION_REGRESSION=PASS
MIGRATION_REGRESSION_RESULT=15 passed
MIGRATION_ZERO_TO_HEAD=PASS
ALEMBIC_CHECK=PASS
PROCUREMENT_APPEND_ONLY=PASS
CURRENT_ITEM_MIGRATION_AUTHORITY=REMOVED
CURRENT_BINDING_MIGRATION_AUTHORITY=REMOVED
IMMUTABLE_SNAPSHOT_AUTHORITY=PASS
FAIL_CLOSED_UNRESOLVED_HISTORY=PASS

FULL_BACKEND_REGRESSION=PASS
BACKEND_RESULT=527 passed, 1 skipped
FULL_FRONTEND_REGRESSION=PASS
FRONTEND_RESULT=147 passed
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_BUILD=PASS
DISPOSABLE_DATABASE_CLEANUP=PASS

PRODUCTION_CHANGED=NO

STATUS=PASS
NEXT_CHECKPOINT=CP-05_PROCUREMENT_UI_CORRECTNESS

CP-04_PROCUREMENT_INTEGRITY=PASS

---

## Checkpoint journal — CP-05 Procurement UI correctness

CHECKPOINT_ID=CP-05
DATE=2026-09-16
BASELINE_BEFORE=471ced2d2d90bc41ebe9c40e4717a0f89c466c14
IMPLEMENTATION_HEAD=5f4fdd9d7b22d776303059fd6e7dc4796ddb55b7
CONSOLIDATED_HEAD=0ca4292879100489994403584b63f6521f7f8e66

IDEMPOTENCY_PAGINATION_RED=ef0c764fdd9b30a9824bd33dc6cb65171afc742f
IDEMPOTENCY_PAGINATION_IMPLEMENTATION=1b00ae509b2a5b58aaa1652552fb09efc27795ee
LOOKUP_PICKER_RED=fad61c6a2d0a55fed31105913c91ba4e1f4dfa1e
LOOKUP_PICKER_IMPLEMENTATION=5f4fdd9d7b22d776303059fd6e7dc4796ddb55b7

STABLE_CLIENT_REQUEST_ID=PASS
LOST_RESPONSE_RETRY=PASS
PROCUREMENT_QUEUE_PAGINATION=PASS
MANAGER_LOOKUP_SEARCH_PAGINATION=PASS
MANUFACTURER_LOOKUP_SEARCH_PAGINATION=PASS
CATALOG_PICKER_PAGINATION=PASS
BINDING_PICKER_PAGINATION=PASS
STALE_SELECTION_RESET=PASS

PROCUREMENT_FRONTEND_CONTRACTS=PASS
PROCUREMENT_FRONTEND_RESULT=18 passed
FULL_FRONTEND_REGRESSION=PASS
FRONTEND_RESULT=147 passed
FRONTEND_TYPECHECK=PASS
FRONTEND_LINT=PASS
FRONTEND_BUILD=PASS
FULL_BACKEND_REGRESSION=PASS
BACKEND_RESULT=527 passed, 1 skipped
DISPOSABLE_DATABASE_CLEANUP=PASS

PRODUCTION_CHANGED=NO

STATUS=PASS
NEXT_CHECKPOINT=CP-06_QUERY_SCALABILITY

CP-05_PROCUREMENT_UI_CORRECTNESS=PASS
