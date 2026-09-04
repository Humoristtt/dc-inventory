# Stage 15 — Production Hardening Before Real Inventory

## Status

    STAGE15=ACTIVE_PREPARATION
    PRODUCTION_SOURCE=9a9ec6a705473d8bd3521b01e6f602284ed9c375
    ALEMBIC_HEAD=a2b3c4d5e6f7
    REAL_INVENTORY_ENTRY=BLOCKED_STAGE15
    STAGE15A_STORAGE=PASS
    STAGE15A_AUTOMATION=IN_IMPLEMENTATION

Stage 15 является production-data gate. Feature backlog Stage 9–14 не обязан
быть завершён до этого hardening, но никакие настоящие складские остатки нельзя
вводить до полного acceptance ниже.

## Authoritative first dataset

Первый planned real inventory dataset:

    ~/dc-inventory-input/sfp-authoritative.xlsx

Он остаётся внешним read-only source и не коммитится в Git.

Contract:

- sheet `На складе`;
- 23 позиции;
- total quantity 265;
- `Модель` → `Item.model`;
- absent P/N → `NULL`;
- QUANTITY accounting;
- no serial-unit synthesis;
- no invented Location;
- no import до снятия Stage 15 gate.

## Stage 15A — Automated off-VM PostgreSQL backup

Production storage interface:

    S3-compatible object storage

Accepted production provider:

    NetApp StorageGRID S3

Production storage coordinates:

    endpoint: https://s3-msk-1.cloudstack.ru
    bucket: dc-inventory-prod-backups
    prefix: postgres/

Provider-specific API не должен проникать в backup domain: endpoint, bucket,
credentials и region задаются configuration/secrets.

Storage boundary acceptance 2026-09-04:

- S3 authentication/read/write PASS;
- Object Lock enabled;
- default retention `GOVERNANCE`, 7 days;
- current object lifecycle expiration 30 days;
- noncurrent version expiration 1 day;
- expired delete-marker cleanup enabled;
- backup identity cannot modify lifecycle;
- backup identity cannot delete objects;
- `BypassGovernanceRetention` не предоставлен.

Backup artifact contract:

- PostgreSQL 18 `pg_dump`;
- custom archive format (`-Fc`);
- no plaintext credentials in command line/logs;
- UTC timestamp in immutable object key;
- source commit SHA in manifest;
- Alembic head in manifest;
- SHA-256 checksum;
- artifact size;
- backup start/completion timestamps;
- upload only after local artifact verification;
- local temporary artifact удаляется после verified off-VM upload;
- manual pre-risky-migration backup использует тот же implementation.

Accepted schedule policy:

    daily
    02:30 Europe/Moscow
    Persistent=true

Accepted retention policy:

    current versions: 30 days
    Object Lock GOVERNANCE: 7 days
    noncurrent versions: 1 day

Retention выполняется контролируемо по backup prefix; незавершённый upload не
может удалить последний verified artifact.

Failure visibility must include:

- non-zero process exit;
- systemd/journal diagnostics;
- explicit last-success / last-failure state;
- artifact key/checksum in successful result;
- отсутствие ложного success при failed upload/verification.

Secrets не хранятся в Git, backup artifact или logs.

## Stage 15B — Real isolated restore acceptance

Restore использует настоящий off-VM artifact, а не same-VM pre-deploy dump.

Temporary restore environment:

- отдельный Docker Compose project;
- отдельная PostgreSQL 18 container/volume/network;
- нет host-published PostgreSQL port;
- production PostgreSQL volume не подключается;
- production runtime containers не меняются;
- environment уничтожается только после сохранения acceptance evidence.

Acceptance:

1. download selected verified artifact;
2. verify SHA-256;
3. `pg_restore --list`;
4. restore into empty isolated PostgreSQL;
5. database opens successfully;
6. Alembic version equals expected head;
7. canonical schema tables exist;
8. critical constraints/indexes/triggers exist;
9. key row counts/invariants are readable;
10. application compatibility check runs against restored DB;
11. projection reconciliation runs read-only;
12. QUANTITY drift = 0;
13. SERIAL drift = 0;
14. restore evidence is recorded in `docs/HISTORY.md`.

Restore test is invalid if it only validates archive syntax without restoring
and opening the database.

## Stage 15C — Final pre-data hardening

Before gate removal:

- full migration status/check;
- destructive-downgrade safety remains PASS;
- full backend/integration/concurrency suite;
- full frontend unit/build/Playwright suite;
- runtime production-shaped CI;
- Telegram gateway CI;
- security/source audit focused on secrets, authz, journal immutability,
  backup credentials and restore isolation;
- production health/live/ready PASS;
- production DB roles/host exposure unchanged;
- production projection reconciliation zero drift;
- canonical docs synchronized;
- authoritative SFP source guard verified.

## Media backup policy

Canonical media subsystem is not yet active.

Therefore media backup is conditional and does not block the first controlled
SFP inventory entry while no canonical user media exists. When Stage 11 media
becomes canonical, media off-VM backup becomes mandatory before media-dependent
production acceptance.

## Rollback policy

Existing same-VM PostgreSQL dumps and Docker image tags remain useful
deploy-specific rollback checkpoints but do not satisfy disaster recovery.

Stage 15 requires:

- verified off-VM DB artifact;
- documented restore path;
- application image/source rollback reference;
- forward-fix policy for migrations that cannot safely downgrade.

No destructive schema downgrade may be used where migration guards prohibit it.

## Gate removal

`REAL_INVENTORY_ENTRY=ALLOWED` may be set only when all are true:

- automated backup PASS;
- verified off-VM artifact PASS;
- retention PASS;
- observable failure path PASS;
- isolated real restore PASS;
- Alembic/schema/invariant verification PASS;
- application compatibility PASS;
- production reconciliation ZERO_DRIFT;
- final CI/security/runtime smoke PASS;
- docs/history updated.

Only after this gate removal may authoritative SFP opening inventory be
performed.
