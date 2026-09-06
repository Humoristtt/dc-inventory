#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "${EUID}" -ne 0 ]; then
    echo "[FATAL] restore rehearsal must run as root" >&2
    exit 1
fi

for command_name in docker git grep mktemp python3 seq sleep tr; do
    command -v "${command_name}" >/dev/null
done
ROOT=/opt/dc-inventory
STATE=/var/lib/dc-inventory-backup/last-success.json
ENV_FILE=/etc/dc-inventory/stage15-backup.env
PG_IMAGE='postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280'
RUN_ID="$(date -u '+%Y%m%dT%H%M%SZ')"
RESTORE_PASSWORD="restore-${RUN_ID}"
WORK_DIR="$(mktemp -d "/var/tmp/dc-inventory-restore.${RUN_ID}.XXXXXX")"
RESTORE_NET="dc-inventory-restore-net-${RUN_ID}"
RESTORE_VOL="dc-inventory-restore-vol-${RUN_ID}"
RESTORE_PG="dc-inventory-restore-pg-${RUN_ID}"
RESTORE_APP="dc-inventory-restore-app-${RUN_ID}"
cleanup_runtime() (
    set +e
    case "${RESTORE_APP:-}" in
        dc-inventory-restore-app-*)
            docker rm -f "$RESTORE_APP" >/dev/null 2>&1 || true
            ;;
    esac

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
docker run --rm \
  --network none \
  -v "$WORK_DIR:/restore:ro" \
  "$PG_IMAGE" \
  pg_restore --list /restore/selected.dump \
  >/dev/null
echo "PG_RESTORE_LIST=PASS"
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
docker exec "$RESTORE_PG" \
  pg_restore \
  --username=dc_inventory_restore \
  --dbname=dc_inventory_restore \
  --no-owner \
  --no-acl \
  /restore/selected.dump
echo "ISOLATED_RESTORE=PASS"
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
docker cp \
  "$ROOT/backend/scripts/reconcile_inventory_projections.sql" \
  "$RESTORE_PG:/tmp/reconcile_inventory_projections.sql"
docker exec "$RESTORE_PG" \
  psql \
  -U dc_inventory_restore \
  -d dc_inventory_restore \
  -v ON_ERROR_STOP=1 \
  -f /tmp/reconcile_inventory_projections.sql
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
cleanup_runtime
trap - EXIT
rm -rf "$WORK_DIR"
echo "ISOLATED_RESTORE_CLEANUP=PASS"
echo "REAL_INVENTORY_ENTRY=BLOCKED_STAGE15"
