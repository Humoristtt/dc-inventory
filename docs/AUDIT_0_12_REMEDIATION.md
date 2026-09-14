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

Status: `OPEN`

### CP-04 — Procurement semantic identity / lifecycle

Status: `OPEN`

### CP-05 — Procurement UI correctness

Status: `OPEN`

### CP-06 — Performance

Status: `OPEN`

### CP-07 — Frontend architecture / HTTP hardening

Status: `OPEN`

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

Execute CP-03 RBAC cross-channel remediation: prove that Web/API and Telegram
authorization use the same capability semantics, preserve the OWNER boundary,
and cannot diverge across administrative access paths.
