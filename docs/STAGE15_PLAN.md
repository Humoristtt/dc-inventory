# Stage 15 — Production Hardening Before Real Inventory

## Status

    STAGE15=ACTIVE_15C
    PRODUCTION_SOURCE=9a9ec6a705473d8bd3521b01e6f602284ed9c375
    PRODUCTION_CHECKOUT=01ff357593eef12e4c47ddc7f3cd9ded70c926ed
    ALEMBIC_HEAD=a2b3c4d5e6f7
    REAL_INVENTORY_ENTRY=BLOCKED_STAGE15
    STAGE15A_STORAGE=PASS
    STAGE15A_AUTOMATION=PASS
    STAGE15A_VERIFIED_BACKUP=PASS
    STAGE15B_REAL_RESTORE=PASS
    STAGE15B_SCHEMA_PARITY=PASS
    STAGE15B_RECONCILIATION=PASS
    STAGE15B_APP_COMPATIBILITY=PASS

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

Production acceptance 2026-09-04:

- PR #29 merged в `main`, production checkout:
  `01ff357593eef12e4c47ddc7f3cd9ded70c926ed`;
- первый verified full artifact:
  `postgres/full/2026/09/04/dc-inventory-20260904T152348Z.dump`;
- manifest:
  `postgres/full/2026/09/04/dc-inventory-20260904T152348Z.manifest.json`;
- dump SHA-256:
  `9c5367121865e7e747115f59073e3c031f2fba52b827ae0a7dba915fbed99f37`;
- dump size: `100822` bytes;
- manifest source checkout:
  `01ff357593eef12e4c47ddc7f3cd9ded70c926ed`;
- manifest Alembic head: `a2b3c4d5e6f7`;
- remote object body read-back и SHA-256 verification PASS;
- Object Lock retention на созданном artifact подтверждён;
- systemd timer `02:30 Europe/Moscow` active и enabled;
- Stage15A automated off-VM backup: `PASS`.

## Stage 15B — Real isolated restore acceptance

Restore использует настоящий off-VM artifact, а не same-VM pre-deploy dump.

Temporary restore environment:

- отдельный isolated PostgreSQL 18 container/volume/network;
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

Production acceptance 2026-09-04:

- использован настоящий verified S3 artifact
  `dc-inventory-20260904T152348Z.dump`;
- download SHA-256 и manifest reconciliation PASS;
- восстановление выполнено в отдельный PostgreSQL 18 container с отдельными
  volume/network и без host-published port;
- `pg_restore` PASS, восстановленная БД открывается;
- public tables: `19`;
- restored Alembic head: `a2b3c4d5e6f7`;
- tables/columns/constraints/indexes/triggers/extensions parity PASS;
- эквивалентные PostgreSQL CHECK-expression cast forms нормализованы при
  semantic comparison; structural constraint parity PASS;
- critical production/restored row-count parity PASS;
- restored baseline:
  `categories=6`, `category_attributes=55`, `items=0`,
  `inventory_units=0`, `stock_balances=0`, `movements=0`,
  `movement_lines=0`;
- QUANTITY drift = `0`;
- SERIAL drift = `0`;
- exact production backend image
  `sha256:4fdb493b9ded2c0dd2fc16f139f16a901189e0b8f8d82552d371ccda31827087`
  успешно поднят против restored DB;
- restored backend `/api/health/ready` PASS без host exposure;
- production runtime оставался healthy и не изменялся;
- temporary restore container/volume/network удалены после acceptance;
- старые same-VM rollback dumps удалены только после успешного S3 restore;
- Stage15B real isolated restore acceptance: `PASS`.

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

Deploy-specific same-VM PostgreSQL dumps from pre-Stage15 checkpoints were
removed on 2026-09-04 only after the verified S3 artifact passed real isolated
restore and application compatibility. Disaster recovery now relies on verified
off-VM S3 artifacts; Docker image/source rollback references remain separate
deployment checkpoints.

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
