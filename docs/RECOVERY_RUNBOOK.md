# Disaster Recovery Runbook — Spikatel Inventory

## Scope

Canonical procedure for restoring a verified off-VM PostgreSQL backup into an
isolated PostgreSQL 18 environment.

The default procedure is a rehearsal. It must not modify the production
PostgreSQL volume or production runtime.

## Safety invariants

During rehearsal:

- production PostgreSQL volume is never mounted;
- restore PostgreSQL has no host-published port;
- `docker compose down -v` is forbidden;
- verified S3 objects are never deleted or overwritten;
- Governance retention is never bypassed;
- destructive Alembic downgrade is forbidden;
- real inventory is not imported;
- `REAL_INVENTORY_MUTATIONS_ENABLED` remains `false`;
- `REAL_INVENTORY_ENTRY` remains `BLOCKED_PENDING_NEXT_ROADMAP`.

## Prerequisites

Production:

    ROOT=/opt/dc-inventory
    STATE=/var/lib/dc-inventory-backup/last-success.json
    ENV_FILE=/etc/dc-inventory/stage15-backup.env

Verify:

    test -r "$STATE"
    test -r "$ENV_FILE"
    cd "$ROOT"
    test -z "$(git status --porcelain)"
    git rev-parse HEAD

Record current production container IDs and `/api/health/live` +
`/api/health/ready` before rehearsal.

## 1. Select verified artifact

Read `last-success.json` and record:

- manifest key;
- dump key;
- SHA-256;
- Alembic head;
- production checkout SHA;
- backend/web runtime provenance.

Final Stage15 recovery acceptance requires manifest schema v2.

`production_checkout_sha` in the manifest is immutable provenance metadata for
the moment the backup was created. A later source-only/documentation commit
does not invalidate the database artifact. Recovery compatibility is proven
against the exact backend/web image IDs and source revisions recorded in the
manifest; a checkout mismatch is recorded as evidence, not treated as an
automatic restore failure.

## 2. Download and verify

Use the configured StorageGRID endpoint, bucket and `S3_PREFIX`.

The selected manifest and dump must:

- exist under the configured backup prefix;
- match remote SHA-256 metadata;
- match locally calculated SHA-256 after download;
- have GOVERNANCE retention;
- match manifest artifact metadata.

Any mismatch is `ABORT`.

## 3. Validate PostgreSQL archive

Use the pinned PostgreSQL 18 image:

    postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280

Run:

    pg_restore --list SELECTED.dump

Failure is `ABORT`.

## 4. Create isolated restore environment

Create resources with a unique prefix:

    dc-inventory-restore-<UTC_RUN_ID>

Required resources:

- one internal Docker network;
- one temporary Docker volume;
- one PostgreSQL 18 container;
- no `-p` host-port publication.

Production `postgres_data` must not appear in restore mounts.

## 5. Restore

Restore into an empty database with:

    pg_restore       --no-owner       --no-acl       --dbname=<isolated-db>       SELECTED.dump

The restore command must finish with exit code 0.

## 6. Verify database

Required checks:

    SELECT version_num FROM alembic_version;

Verify canonical tables and critical row counts.

For the current pre-real-data baseline the expected operational rows remain:

    items=0
    inventory_units=0
    stock_balances=0
    movements=0
    movement_lines=0

Do not hard-code these zero counts after real inventory entry.

## 7. Projection reconciliation

Run:

    backend/scripts/reconcile_inventory_projections.sql

Required result:

    QUANTITY drift = 0
    SERIAL drift = 0

Any returned drift row is a data-integrity blocker.

## 8. Application compatibility

From manifest schema v2 read:

- backend immutable image ID;
- backend source revision;
- web immutable image ID;
- web source revision.

For backend-family services the recorded image/revision must agree.

Run the exact available backend artifact against the isolated restored database
without host exposure and require `/api/health/ready` to pass.

If the exact application artifact is unavailable, record
`APPLICATION_ARTIFACT_MISSING` and prohibit production cutover. Durable off-VM
application artifact is handled by AUD-04.

## 9. Evidence

Preserve:

- selected dump/manifest keys;
- checksums;
- manifest schema version;
- production checkout SHA;
- runtime image IDs/revisions;
- Alembic head;
- row counts;
- reconciliation results;
- compatibility result;
- UTC start/end;
- production container IDs and health before/after.

## 10. Cleanup

Only after evidence is saved:

- remove temporary restore application container;
- remove temporary PostgreSQL container;
- remove temporary restore volume;
- remove temporary internal network;
- remove temporary downloaded files.

Before removal, verify every resource name begins with
`dc-inventory-restore-`.

Re-check production container IDs and health after cleanup.

## 10A. Guarded command-level rehearsal

Canonical executable procedure:

    ops/recovery/rehearse_restore.sh

После merge/deploy соответствующего release rehearsal запускается только
явным operator action:

    sudo -n bash ops/recovery/rehearse_restore.sh

Script fail-closed проверяет S3 manifest/hash/retention, isolated PostgreSQL 18
restore, Alembic head, projection reconciliation, exact backend image
compatibility, cleanup и неизменность production runtime.

Он не выполняет production cutover и не включает real-inventory mutations.

## 11. Production cutover boundary

This runbook does not authorize or automatically execute production cutover.

Production recovery requires a separate incident/change decision and:

1. inventory mutation gate remains closed;
2. fresh canonical production backup;
3. selected artifact verification PASS;
4. isolated restore rehearsal PASS;
5. exact durable application artifact available;
6. migration compatibility/forward-fix plan approved;
7. explicit target volume/config review;
8. abort criteria recorded before modification;
9. post-cutover health PASS;
10. post-cutover reconciliation ZERO_DRIFT.

In-place overwrite of the existing production PostgreSQL volume is not an
accepted rehearsal procedure.
