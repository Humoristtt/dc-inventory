# Stage 15C — Full Audit Remediation Tracker

This document tracks findings from the full-project audit performed before
real inventory entry.

Closure state:

    STAGE15=TECHNICAL_HARDENING_COMPLETE
    STAGE15_GATE_DECISION=KEEP_DISABLED_NEXT_ROADMAP
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP

No real inventory import or manual real inventory entry is allowed until the
complete Stage 15C acceptance and a separate explicit operational decision.

## Audit baseline

    BASE_MAIN=811fb55750bed67e6773c5a84d5d459b4ff67e71
    ALEMBIC_HEAD=a2b3c4d5e6f7

## Remediation queue

- [x] AUD-00 — scheduled backup from current main verified.
- [x] AUD-01 — server-side real-inventory mutation gate.
- [x] AUD-02 — backup manifest runtime provenance v2.
- [x] AUD-03 — S3 lifecycle prefix validation.
- [x] AUD-04 — durable immutable application rollback artifact.
- [x] AUD-05 — controlled production backup failure drill.
- [x] AUD-06 — command-level disaster-recovery runbook.
- [x] AUD-07 — stale inventory-source assumptions retired; no real-data source defined.
- [x] AUD-08 — PRODUCT_REQUIREMENTS current-state reconciliation.
- [x] AUD-09 — DEVELOPMENT current-state reconciliation.
- [x] AUD-10 — ARCHITECTURE current-state reconciliation.
- [x] AUD-11 — README / DEPLOYMENT Stage 15 wording reconciliation.
- [x] AUD-12 — OPERATIONS / ROADMAP / STAGE15_PLAN / HISTORY reconciliation.
- [x] AUD-13 — current-state documentation freshness CI guard.
- [x] AUD-14 — dependency/container vulnerability scanning policy.
- [x] AUD-15 — worker health/observability.
- [x] AUD-16 — Docker logging/resource policy.
- [x] AUD-17 — production host-level read-only security audit.
- [x] AUD-18 — Telegram at-least-once delivery semantics documentation.
- [x] AUD-19 — repository visibility decision before real inventory.
- [x] AUD-20 — final full source/security re-audit after remediation.
- [x] AUD-21 — final production acceptance.
- [x] AUD-22 — final Stage 15 documentation closure.
- [x] AUD-23 — explicit Stage 15 gate removal decision.
- [x] AUD-24 — real data entry deferred to next roadmap; separate explicit operator action only.

## AUD-00 evidence

Accepted scheduled production backup:

    started_at_utc=2026-09-05T23:30:06Z
    verified_at_utc=2026-09-05T23:30:08Z
    source_checkout_sha=811fb55750bed67e6773c5a84d5d459b4ff67e71
    alembic_head=a2b3c4d5e6f7
    dump_key=postgres/full/2026/09/05/dc-inventory-20260905T233006Z.dump
    dump_sha256=7caf889420d1342bb480da1c02c2089f1a33286ed5cd311813d1a1ab97fc44f0
    dump_size_bytes=100901
    remote_verification=PASS
    temp_cleanup=PASS
    backup_lock=FREE
    production_health=PASS

## AUD-01 evidence

Production acceptance 2026-09-06:

    PR=32
    MERGE_SHA=cdfd1b7f9b3c5a6fb225ed52f92dcaed86313872
    RUNTIME_GATE_HTTP_423=PASS
    MUTATION_ROUTE_REGISTRATION=PASS
    ALEMBIC_HEAD=a2b3c4d5e6f7
    items=0
    inventory_units=0
    stock_balances=0
    movements=0
    movement_lines=0
    PRODUCTION_HEALTH=PASS
    AUD_01=PASS
    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP

## Batch A

Grouped source remediation:

    AUD-02
    AUD-03
    AUD-06
    AUD-08..AUD-13

Accepted after required CI and production evidence:

    PR_33=MERGED
    PR_34=MERGED
    AUD_02=PASS
    AUD_03=PASS
    AUD_06=PASS
    AUD_08_13=PASS
    BATCH_A=PASS


## Batch B

Accepted production evidence:

    AUD_04=PASS
    ROLLBACK_OBJECT_LOCK=PASS
    ROLLBACK_BUNDLE_SHA256=731b20644c41351e302f58b9bbeea0279f73823bd80f5ef48bc299f1df0fc94a
    AUD_05=PASS
    AUD05_FAILURE_DRILL=PASS
    AUD05_RECOVERY_AFTER_FAILURE=PASS
    LAST_SUCCESS_DUMP=postgres/full/2026/09/06/dc-inventory-20260906T215601Z.dump
    LAST_SUCCESS_SHA256=62c3e71d3921968865dae3e4bb10e82c09228b22ecfa80fa5befdd61b4ce01a3
    AUD_07=PASS
    BATCH_B=PASS

## Batch C security decisions

Host audit is read-only. Recorded baseline does not claim that UFW is
enabled and does not silently change SSH/network policy.

    AUD17_HOST_AUDIT=READ_ONLY_RECORDED
    UFW_STATUS=INACTIVE_RECORDED_FINDING
    REPOSITORY_VISIBILITY_CURRENT=public
    REPOSITORY_VISIBILITY_BEFORE_REAL_INVENTORY=REASSESS_REQUIRED
    AUD19_DECISION=REASSESS_BEFORE_REAL_INVENTORY

Real inventory remains blocked by the explicit fail-closed gate decision even
though technical Stage15 hardening is complete.

### AUD-14 first CI evidence

Initial Trivy runtime scan on PR #36 correctly blocked the backend image.

Detected Debian 12.15 CRITICAL findings without an available fixed version:

    CVE-2025-7458  libsqlite3-0  status=affected
    CVE-2026-13221 perl-base     status=affected
    CVE-2026-42496 perl-base     status=fix_deferred
    CVE-2026-8376  perl-base     status=affected
    CVE-2023-45853 zlib1g        status=will_not_fix

CI policy therefore distinguishes current upstream-unfixed findings from
remediable CRITICAL vulnerabilities:

    CRITICAL_FIX_AVAILABLE=BLOCK
    CRITICAL_NO_FIX_AVAILABLE=RECORDED_NOT_BLOCKING

The findings remain subject to review when pinned base-image digests are
updated or during the final Stage15 security re-audit.

### AUD-14 PostgreSQL scoped exception

The pinned official PostgreSQL 18 image currently contains:

    TARGET=/usr/local/bin/gosu
    CVE=CVE-2025-68121
    SEVERITY=CRITICAL
    INSTALLED_GO=v1.24.6
    FIX_AVAILABLE=YES

The current upstream `postgres:18` tag still resolves to the already pinned
digest, so an image refresh does not remediate the finding.

A narrowly scoped Trivy exception is therefore recorded in:

    ops/security/trivy-postgres.ignore.yaml

The exception applies only to:

    CVE-2025-68121
    path=/usr/local/bin/gosu
    expires=2026-10-07

All other fixable CRITICAL vulnerabilities remain blocking.

POSTGRES_SCOPED_EXCEPTION=PASS
AUD14_POSTGRES_SCAN_POLICY=PASS


## Batch C acceptance

    PR_36=MERGED
    MERGE_SHA=b53c4213f474073c230eab24bdc70891a7ffd7f7
    REQUIRED_CI=PASS
    AUD_14=PASS
    AUD_15=PASS
    AUD_16=PASS
    AUD_17=PASS_RECORDED_FINDINGS
    AUD_18=PASS
    AUD_19=PASS_REASSESS_BEFORE_REAL_INVENTORY
    BATCH_C_PRODUCTION_ACCEPTANCE=PASS
    BATCH_C=PASS

## Batch D closure

    AUD_20=PASS
    AUD_21=PASS
    AUD_22=PASS
    AUD_23=PASS_KEEP_DISABLED
    AUD_24=DEFERRED_NEXT_ROADMAP
    STAGE15_GATE_DECISION=KEEP_DISABLED_NEXT_ROADMAP
    CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED
    REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP
    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP
    BATCH_D=PASS
    STAGE15=TECHNICAL_HARDENING_COMPLETE

No real inventory import or manual real-inventory entry was performed as part of
Stage15 closure.
