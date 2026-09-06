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
- `REAL_INVENTORY_ENTRY` remains `BLOCKED_STAGE15`.

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

Ниже — reproducible isolated restore sequence. Его выполняют только на
production VM после принятия соответствующего release.

Команды запускаются в subshell, поэтому strict shell mode не изменяет
родительскую interactive shell:

    (
    set -euo pipefail
    umask 077

    ROOT=/opt/dc-inventory
    STATE=/var/lib/dc-inventory-backup/last-success.json
    ENV_FILE=/etc/dc-inventory/stage15-backup.env

    PG_IMAGE='postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280'

    RUN_ID="$(date -u '+%Y%m%dT%H%M%SZ')"
    WORK_DIR="$(mktemp -d "/var/tmp/dc-inventory-restore.${RUN_ID}.XXXXXX")"

    RESTORE_NET="dc-inventory-restore-net-${RUN_ID}"
    RESTORE_VOL="dc-inventory-restore-vol-${RUN_ID}"
    RESTORE_PG="dc-inventory-restore-pg-${RUN_ID}"

    cleanup_runtime() {
        set +e

        case "${RESTORE_PG:-}" in
            dc-inventory-restore-pg-*)
                docker rm -f "$RESTORE_PG" >/dev/null 2>&1 || true
                ;;
        esac

        case "${RESTORE_VOL:-}" in
            dc-inventory-restore-vol-*)
                docker volume rm "$RESTORE_VOL" >/dev/null 2>&1 || true
                ;;
        esac

        case "${RESTORE_NET:-}" in
            dc-inventory-restore-net-*)
                docker network rm "$RESTORE_NET" >/dev/null 2>&1 || true
                ;;
        esac
    }

    trap cleanup_runtime EXIT

    test -r "$STATE"
    test -r "$ENV_FILE"
    test -d "$ROOT/.git"

    cd "$ROOT"

    test -z "$(
        git -c safe.directory="$ROOT" status --porcelain
    )"

    PRODUCTION_CHECKOUT_SHA="$(
        git -c safe.directory="$ROOT" rev-parse HEAD
    )"

    MANIFEST_KEY="$(
        python3 -c '
    import json
    import sys
    from pathlib import Path

    state = json.loads(Path(sys.argv[1]).read_text())

    if state.get("state") != "success":
        raise SystemExit("backup state is not success")

    print(state["manifest_key"])
    ' "$STATE"
    )"

    echo "PRODUCTION_CHECKOUT_SHA=$PRODUCTION_CHECKOUT_SHA"
    echo "MANIFEST_KEY=$MANIFEST_KEY"

Download and verify the selected manifest/dump using the same read-only S3
configuration as the backup service:

    python3 - \
      "$ROOT/ops/backup/s3_stage15.py" \
      "$ENV_FILE" \
      "$MANIFEST_KEY" \
      "$WORK_DIR" <<'PY'
    import importlib.util
    import json
    import sys
    from pathlib import Path

    helper_path = Path(sys.argv[1])
    env_path = Path(sys.argv[2])
    manifest_key = sys.argv[3]
    work_dir = Path(sys.argv[4])

    sys.path.insert(0, str(helper_path.parent))

    spec = importlib.util.spec_from_file_location(
        "stage15_s3",
        helper_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    env = module.load_env(env_path)
    client = module.make_client(env)
    module.validate_storage(client, env)

    bucket = env["S3_BUCKET"]
    prefix = env["S3_PREFIX"].rstrip("/") + "/"

    if not manifest_key.startswith(prefix):
        raise RuntimeError(
            "manifest is outside configured prefix"
        )

    manifest_path = work_dir / "selected.manifest.json"

    client.download_file(
        bucket,
        manifest_key,
        str(manifest_path),
    )

    manifest_head = client.head_object(
        Bucket=bucket,
        Key=manifest_key,
    )

    expected_manifest_sha = (
        manifest_head.get("Metadata", {}).get("sha256")
    )

    if not expected_manifest_sha:
        raise RuntimeError(
            "manifest has no remote sha256 metadata"
        )

    if (
        module.sha256_file(manifest_path)
        != expected_manifest_sha
    ):
        raise RuntimeError(
            "manifest checksum mismatch"
        )

    manifest = json.loads(manifest_path.read_text())

    if manifest.get("schema_version") != 2:
        raise RuntimeError(
            "Stage15 final recovery requires manifest schema v2"
        )

    dump_key = manifest["artifact"]["key"]
    expected_dump_sha = manifest["artifact"]["sha256"]

    if not dump_key.startswith(prefix):
        raise RuntimeError(
            "dump is outside configured prefix"
        )

    dump_path = work_dir / "selected.dump"

    client.download_file(
        bucket,
        dump_key,
        str(dump_path),
    )

    dump_head = client.head_object(
        Bucket=bucket,
        Key=dump_key,
    )

    if (
        dump_head.get("Metadata", {}).get("sha256")
        != expected_dump_sha
    ):
        raise RuntimeError(
            "dump remote checksum metadata mismatch"
        )

    if module.sha256_file(dump_path) != expected_dump_sha:
        raise RuntimeError(
            "downloaded dump checksum mismatch"
        )

    for key in (manifest_key, dump_key):
        retention = client.get_object_retention(
            Bucket=bucket,
            Key=key,
        ).get("Retention", {})

        if retention.get("Mode") != "GOVERNANCE":
            raise RuntimeError(
                f"{key} has no GOVERNANCE retention"
            )

    print("RESTORE_DOWNLOAD_VERIFICATION=PASS")
    PY

Validate the archive before creating any restore database:

    docker run --rm \
      --network none \
      -v "$WORK_DIR:/restore:ro" \
      "$PG_IMAGE" \
      pg_restore --list /restore/selected.dump \
      >/dev/null

    echo "PG_RESTORE_LIST=PASS"

Create an internal-only PostgreSQL restore environment:

    docker network create --internal "$RESTORE_NET"
    docker volume create "$RESTORE_VOL"

    docker run -d \
      --name "$RESTORE_PG" \
      --network "$RESTORE_NET" \
      -e POSTGRES_DB=dc_inventory_restore \
      -e POSTGRES_USER=dc_inventory_restore \
      -e POSTGRES_PASSWORD="restore-${RUN_ID}" \
      -v "$RESTORE_VOL:/var/lib/postgresql" \
      -v "$WORK_DIR:/restore:ro" \
      "$PG_IMAGE" \
      >/dev/null

    for attempt in $(seq 1 60); do
        if docker exec "$RESTORE_PG" \
          pg_isready \
          -U dc_inventory_restore \
          -d dc_inventory_restore \
          >/dev/null 2>&1; then
            break
        fi

        sleep 1
    done

    docker exec "$RESTORE_PG" \
      pg_isready \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      >/dev/null

Restore the verified dump:

    docker exec "$RESTORE_PG" \
      pg_restore \
      --username=dc_inventory_restore \
      --dbname=dc_inventory_restore \
      --no-owner \
      --no-acl \
      /restore/selected.dump

    echo "ISOLATED_RESTORE=PASS"

Verify Alembic and critical row counts:

    docker exec "$RESTORE_PG" \
      psql \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      -v ON_ERROR_STOP=1 \
      -At \
      -c 'SELECT version_num FROM alembic_version;'

    docker exec "$RESTORE_PG" \
      psql \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      -v ON_ERROR_STOP=1 \
      -At \
      -c "
        SELECT 'items=' || count(*) FROM items;
        SELECT 'inventory_units=' || count(*) FROM inventory_units;
        SELECT 'stock_balances=' || count(*) FROM stock_balances;
        SELECT 'movements=' || count(*) FROM movements;
        SELECT 'movement_lines=' || count(*) FROM movement_lines;
      "

Run canonical projection reconciliation:

    docker cp \
      "$ROOT/backend/scripts/reconcile_inventory_projections.sql" \
      "$RESTORE_PG:/tmp/reconcile_inventory_projections.sql"

    docker exec "$RESTORE_PG" \
      psql \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      -v ON_ERROR_STOP=1 \
      -f /tmp/reconcile_inventory_projections.sql

Required result is zero QUANTITY and SERIAL drift.

Before production cutover, verify the exact runtime artifacts recorded by
manifest schema v2 are locally available:

    BACKEND_IMAGE_ID="$(
        python3 -c '
    import json
    import sys
    from pathlib import Path

    manifest = json.loads(Path(sys.argv[1]).read_text())
    print(manifest["runtime"]["backend"]["image_id"])
    ' "$WORK_DIR/selected.manifest.json"
    )"

    WEB_IMAGE_ID="$(
        python3 -c '
    import json
    import sys
    from pathlib import Path

    manifest = json.loads(Path(sys.argv[1]).read_text())
    print(manifest["runtime"]["web"]["image_id"])
    ' "$WORK_DIR/selected.manifest.json"
    )"

    docker image inspect "$BACKEND_IMAGE_ID" >/dev/null
    docker image inspect "$WEB_IMAGE_ID" >/dev/null

    echo "EXACT_RUNTIME_ARTIFACTS_LOCAL=PASS"

After evidence has been copied outside the temporary directory:

    cleanup_runtime
    trap - EXIT

    rm -rf "$WORK_DIR"

    echo "ISOLATED_RESTORE_CLEANUP=PASS"
    echo "REAL_INVENTORY_ENTRY=BLOCKED_STAGE15"
    )

The rehearsal is accepted only if production container IDs and live/ready
health recorded after cleanup match the expected unchanged production runtime.

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
