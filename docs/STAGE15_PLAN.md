# Stage 15 — Production Hardening Before Real Inventory

## Status

    STAGE15=ACTIVE_15C
    PRODUCTION_SOURCE=9a9ec6a705473d8bd3521b01e6f602284ed9c375
    STAGE15C_CHECKOUT_SYNC_BASELINE=7d46920c659a86ef919cc2b1f64decce973d39ab
    ALEMBIC_HEAD=a2b3c4d5e6f7
    REAL_INVENTORY_ENTRY=BLOCKED_STAGE15
    STAGE15A_STORAGE=PASS
    STAGE15A_AUTOMATION=PASS
    STAGE15A_VERIFIED_BACKUP=PASS
    STAGE15A_SCHEDULED_RUN=PASS
    STAGE15B_REAL_RESTORE=PASS
    STAGE15B_SCHEMA_PARITY=PASS
    STAGE15B_RECONCILIATION=PASS
    STAGE15B_APP_COMPATIBILITY=PASS
    STAGE15C_CHECKOUT_SYNC=PASS
    STAGE15C_LOCAL_BACKUP_HYGIENE=PASS

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
- первый автоматический scheduled production run подтверждён:
  `2026-09-04T23:30:01Z` (`2026-09-05 02:30 Europe/Moscow`);
- scheduled dump:
  `postgres/full/2026/09/04/dc-inventory-20260904T233001Z.dump`;
- scheduled dump SHA-256:
  `4c54098b53a2636614373b44f7894d3f95a32e334c964900a14dec3b5539ce74`;
- scheduled dump size: `100901` bytes;
- scheduled run Alembic head: `a2b3c4d5e6f7`;
- scheduled remote verification PASS;
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

Completed checkpoints 2026-09-06:

- production Git checkout docs-only fast-forward:
  `01ff357593eef12e4c47ddc7f3cd9ded70c926ed` →
  `7d46920c659a86ef919cc2b1f64decce973d39ab`;
- changed checkout content was documentation only;
- production runtime container IDs remained unchanged;
- health/live/ready after checkout sync PASS;
- permanent local PostgreSQL backup artifacts: `0`;
- Stage15 temporary backup workdirs: `0`;
- empty legacy directories
  `/home/install/.dc-inventory-db-backups` and
  `/opt/dc-inventory/backups` removed with `rmdir` only after emptiness check;
- one explicit environment/config rollback artifact preserved:
  `/home/install/.dc-inventory-env-backups/env-pre-stage6-deploy`;
- preserved env rollback size `698` bytes; SHA-256
  `350535df2631887159486587c13758ceb83c376cecb02967ab0d671cf3bd29f7`;
- `/var/lib/dc-inventory-backup` remains operational state/observability,
  not backup artifact storage;
- verified off-VM StorageGRID S3 remains authoritative PostgreSQL recovery
  storage;
- permanent accumulation of manual local PostgreSQL dumps on production VM is
  prohibited.

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

Rollback/recovery boundaries are intentionally separate.

### PostgreSQL recovery

Verified off-VM StorageGRID S3 artifacts are the authoritative PostgreSQL
disaster-recovery source.

Deploy-specific same-VM PostgreSQL dumps from pre-Stage15 checkpoints were
removed only after successful real isolated restore acceptance. Permanent local
PostgreSQL dump accumulation on production VM is not part of the accepted
operating model.

Manual pre-risky-migration database backup must use the canonical Stage15
backup implementation/off-VM policy rather than create a new unmanaged
collection of local dumps.

### Application source/image rollback

Application source/image rollback references are deployment checkpoints and are
separate from database disaster recovery. Final immutable application image
deployment/rollback decision remains a Stage15C item.

### Environment/config rollback

The explicitly preserved local environment/config rollback checkpoint is:

    /home/install/.dc-inventory-env-backups/env-pre-stage6-deploy

It is not a PostgreSQL backup.

Recorded properties:

- size: `698` bytes;
- mode: `600`;
- owner: `install:install`;
- SHA-256:
  `350535df2631887159486587c13758ceb83c376cecb02967ab0d671cf3bd29f7`.

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
