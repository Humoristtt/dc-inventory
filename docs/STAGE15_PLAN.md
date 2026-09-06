# Stage 15 — Production Hardening Before Real Inventory

## Status

    STAGE15=TECHNICAL_HARDENING_COMPLETE
    ALEMBIC_HEAD=a2b3c4d5e6f7
    REAL_INVENTORY_MUTATIONS_ENABLED=false
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
    AUD_00=PASS
    AUD_01=PASS
    AUD_02=PASS
    AUD_03=PASS
    AUD_06=PASS
    AUD_08_13=PASS
    BATCH_A=PASS
    BATCH_B=PASS
    AUD_14_19=PASS
    BATCH_C=PASS
    AUD_20=PASS
    AUD_21=PASS
    AUD_22=PASS
    STAGE15_GATE_DECISION=KEEP_DISABLED_NEXT_ROADMAP
    AUD_23=PASS_KEEP_DISABLED
    AUD_24=DEFERRED_NEXT_ROADMAP
    BATCH_D=PASS

Stage 15 technical hardening завершён. Feature backlog Stage 9–14 не является
частью этого acceptance. Реальные складские данные по-прежнему нельзя вводить:
отдельный fail-closed operational gate намеренно оставлен закрытым до следующего roadmap.

## Real inventory source boundary

Источник первого реального наполнения склада сейчас намеренно не определён.

    CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED
    REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP

Ни один существующий spreadsheet, workbook или локальный файл не является
accepted real-inventory source.

Новый domain/import contract, mapping и способ первоначального наполнения будут
определены после Stage 15 в следующем roadmap.

AUD-24 не выполняет импорт автоматически и остаётся отдельным explicit operator
action после нового продуктового решения.

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
- manifest schema v2;
- production Git checkout SHA;
- backend immutable image ID + source revision;
- telegram-worker immutable image ID + source revision;
- maintenance-worker immutable image ID + source revision;
- web immutable image ID + source revision;
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

Canonical command-level recovery/rehearsal procedure:

    docs/RECOVERY_RUNBOOK.md

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
- real-inventory source remains intentionally undefined and stale source assumptions are retired.

## Final Stage 15C technical acceptance

Production acceptance base:

    MERGE_SHA=b53c4213f474073c230eab24bdc70891a7ffd7f7
    ALEMBIC_HEAD=a2b3c4d5e6f7
    BATCH_C_PRODUCTION_ACCEPTANCE=PASS
    AUD17_FINAL_HOST_RECHECK=PASS
    AUD23_PRECONDITION_HOST_RECHECK=PASS
    REAL_INVENTORY_MUTATIONS_ENABLED=false

Accepted runtime evidence:

- backend, web, PostgreSQL and both workers healthy;
- migrate and db-permissions exited `0`;
- backend/web OCI revisions equal accepted merge SHA;
- PostgreSQL remains on the pinned digest and persistent named volume;
- post-deploy DB counts unchanged;
- QUANTITY reconciliation drift `0`;
- SERIAL reconciliation drift `0`;
- worker heartbeat healthchecks PASS;
- runtime logging/PID/security boundaries PASS;
- no PostgreSQL/backend/worker host ports published;
- web published only on `127.0.0.1:8080`;
- `/healthz`, live and ready health endpoints PASS;
- runtime restart counters `0`;
- SSH root/password/kbd-interactive authentication disabled;
- UFW inactive, X11 forwarding enabled and TCP forwarding enabled remain
  recorded host findings rather than silently changed policy.

Repository visibility remains `public` with mandatory reassessment before any
real inventory dataset or gate removal.

## Media backup policy

Canonical media subsystem is not yet active.

Therefore media backup is conditional and does not block technical hardening
closure while no canonical user media exists. When Stage 11 media
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
separate from database disaster recovery. Immutable application rollback artifact and exact runtime provenance were
accepted during Stage15C.

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

## Gate decision and technical closure

Stage15 technical hardening is complete, but completion does not authorize real
inventory entry.

Current explicit decision:

    STAGE15_GATE_DECISION=KEEP_DISABLED_NEXT_ROADMAP
    REAL_INVENTORY_MUTATIONS_ENABLED=false
    REAL_INVENTORY_ENTRY=BLOCKED_STAGE15
    CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED
    REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP

AUD-23 is closed by an explicit decision to keep the fail-closed gate disabled.
AUD-24 is closed as a deferral decision: no import, opening balance load or
manual real-inventory population is performed by Stage15.

The next product roadmap must define the updated product vision, domain/data
entry contract and real-inventory source. Only after that separate design and a
new explicit operational decision may the mutation/data-entry gate be
reconsidered.
