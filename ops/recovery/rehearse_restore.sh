#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [ "${EUID}" -ne 0 ]; then
    echo "[FATAL] restore rehearsal must run as root" >&2
    exit 1
fi

for command_name in curl date docker git grep mktemp python3 rm seq sleep tr; do
    command -v "${command_name}" >/dev/null
done
ROOT=/opt/dc-inventory
STATE=/var/lib/dc-inventory-backup/last-success.json
ENV_FILE=/etc/dc-inventory/stage15-backup.env
PG_IMAGE='postgres:18@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280'
RUN_ID="$(date -u '+%Y%m%dT%H%M%SZ')"
WORK_DIR="$(mktemp -d "/var/tmp/dc-inventory-restore.${RUN_ID}.XXXXXX")"
RUN_ID="${RUN_ID}-${WORK_DIR##*.}"
RESTORE_NET="dc-inventory-restore-net-${RUN_ID}"
RESTORE_VOL="dc-inventory-restore-vol-${RUN_ID}"
RESTORE_PG="dc-inventory-restore-pg-${RUN_ID}"
RESTORE_APP="dc-inventory-restore-app-${RUN_ID}"
RESTORE_NET_CREATED=false
RESTORE_VOL_CREATED=false
RESTORE_PG_CREATED=false
RESTORE_APP_CREATED=false
cleanup_runtime() (
    set +e
    case "${RESTORE_APP_CREATED}:${RESTORE_APP:-}" in
        true:dc-inventory-restore-app-*)
            docker rm -f "$RESTORE_APP" >/dev/null 2>&1 || true
            ;;
    esac

    case "${RESTORE_PG_CREATED}:${RESTORE_PG:-}" in
        true:dc-inventory-restore-pg-*)
            docker rm -f "$RESTORE_PG" >/dev/null 2>&1 || true
            ;;
    esac
    case "${RESTORE_VOL_CREATED}:${RESTORE_VOL:-}" in
        true:dc-inventory-restore-vol-*)
            docker volume rm "$RESTORE_VOL" >/dev/null 2>&1 || true
            ;;
    esac
    case "${RESTORE_NET_CREATED}:${RESTORE_NET:-}" in
        true:dc-inventory-restore-net-*)
            docker network rm "$RESTORE_NET" >/dev/null 2>&1 || true
            ;;
    esac

    case "${WORK_DIR:-}" in
        /var/tmp/dc-inventory-restore.*)
            rm -rf -- "$WORK_DIR" >/dev/null 2>&1 || true
            ;;
    esac
)
trap cleanup_runtime EXIT
RESTORE_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
test -r "$STATE"
test -r "$ENV_FILE"
test -d "$ROOT/.git"
cd "$ROOT"
test -z "$(
    git -c safe.directory="$ROOT" status --porcelain
)"

production_id() {
    local service="$1"
    local container_id

    container_id="$(docker compose ps -q "$service")"
    test -n "$container_id"
    printf '%s' "$container_id"
}

production_health() {
    python3 - <<'HEALTH'
import json
import subprocess

domain = "app.spik-inventory.ru"
resolve = f"{domain}:443:127.0.0.1"

for path, expected in (
    ("/api/health/live", "ok"),
    ("/api/health/ready", "ready"),
):
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--resolve",
            resolve,
            f"https://{domain}{path}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    payload = json.loads(result.stdout)

    if payload.get("status") != expected:
        raise SystemExit(
            f"{path}: unexpected payload {payload!r}"
        )
HEALTH
}

PROD_BACKEND_BEFORE="$(production_id backend)"
PROD_WEB_BEFORE="$(production_id web)"
PROD_TELEGRAM_BEFORE="$(production_id telegram-worker)"
PROD_MAINTENANCE_BEFORE="$(production_id maintenance-worker)"
PROD_POSTGRES_BEFORE="$(production_id postgres)"
if docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
    "$PROD_BACKEND_BEFORE" | grep -qx 'EMAIL_DELIVERY_ENABLED=true'; then
    PROD_EMAIL_ENABLED=true
    PROD_EMAIL_BEFORE="$(production_id email-worker)"
else
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
        "$PROD_BACKEND_BEFORE" | grep -qx 'EMAIL_DELIVERY_ENABLED=false'
    PROD_EMAIL_ENABLED=false
    PROD_EMAIL_BEFORE=""
    test -z "$(docker compose ps -q email-worker)"
fi

production_health

docker inspect     --format '{{range .Config.Env}}{{println .}}{{end}}'     "$PROD_BACKEND_BEFORE"     | grep -qx 'REAL_INVENTORY_MUTATIONS_ENABLED=false'

echo "PRODUCTION_PRECHECK=PASS"

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
  "$WORK_DIR" \
  "$PRODUCTION_CHECKOUT_SHA" \
  "$STATE" <<'PY'
import importlib.util
import json
import sys
from pathlib import Path
helper_path = Path(sys.argv[1])
env_path = Path(sys.argv[2])
manifest_key = sys.argv[3]
work_dir = Path(sys.argv[4])
production_checkout_sha = sys.argv[5]
state = json.loads(Path(sys.argv[6]).read_text(encoding="utf-8"))
if state.get("schema_version") != 2 or state.get("state") != "success":
    raise RuntimeError("Invalid selected backup state")
sys.path.insert(0, str(helper_path.parent))
sys.path.insert(0, str(helper_path.parent.parent / "recovery"))
from validate_manifest import validate_manifest
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
def require_version_id(value):
    if (
        not isinstance(value, str)
        or not value
        or value == "null"
        or value.strip() != value
    ):
        raise RuntimeError("Invalid or missing S3 VersionId")
    return value


manifest_version = state.get("manifest_version_id")
state_dump_version = state.get("dump_version_id")

if (manifest_version is None) != (state_dump_version is None):
    raise RuntimeError("Incomplete backup version provenance")

if manifest_version is None:
    # Legacy state: resolve the current version exactly once.
    current = client.head_object(
        Bucket=bucket,
        Key=manifest_key,
    )
    manifest_version = current.get("VersionId")

manifest_version = require_version_id(manifest_version)

manifest_head = client.head_object(
    Bucket=bucket,
    Key=manifest_key,
    VersionId=manifest_version,
)
if manifest_head.get("VersionId") not in (None, manifest_version):
    raise RuntimeError("Manifest HEAD returned another version")

manifest_path = work_dir / "selected.manifest.json"
client.download_file(
    bucket,
    manifest_key,
    str(manifest_path),
    ExtraArgs={"VersionId": manifest_version},
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
manifest = validate_manifest(json.loads(manifest_path.read_text()), manifest_key, prefix)

if (
    state["manifest_key"] != manifest_key
    or state["dump_key"] != manifest["artifact"]["key"]
    or state["dump_sha256"] != manifest["artifact"]["sha256"]
    or state["dump_size_bytes"] != manifest["artifact"]["size_bytes"]
    or state["runtime"] != manifest["runtime"]
):
    raise RuntimeError("Backup state and manifest provenance mismatch")

manifest_checkout_sha = manifest.get("production_checkout_sha")

print(
    "BACKUP_PRODUCTION_CHECKOUT_SHA="
    f"{manifest_checkout_sha}"
)
print("RESTORE_MANIFEST_CHECKOUT_METADATA=PASS")

if manifest_checkout_sha == production_checkout_sha:
    print("RESTORE_MANIFEST_CHECKOUT_MATCH=YES")
else:
    print("RESTORE_MANIFEST_CHECKOUT_MATCH=NO")

dump_key = manifest["artifact"]["key"]
expected_dump_sha = manifest["artifact"]["sha256"]
if not dump_key.startswith(prefix):
    raise RuntimeError(
        "dump is outside configured prefix"
    )
manifest_dump_version = manifest["artifact"].get("version_id")

if state_dump_version is not None:
    if manifest_dump_version != state_dump_version:
        raise RuntimeError("Manifest and state dump VersionIds differ")
    dump_version = require_version_id(state_dump_version)
elif manifest_dump_version is not None:
    dump_version = require_version_id(manifest_dump_version)
else:
    # Legacy manifest: pin current dump once, then verify its SHA-256.
    current = client.head_object(Bucket=bucket, Key=dump_key)
    dump_version = require_version_id(current.get("VersionId"))

dump_head = client.head_object(
    Bucket=bucket,
    Key=dump_key,
    VersionId=dump_version,
)
if dump_head.get("VersionId") not in (None, dump_version):
    raise RuntimeError("Dump HEAD returned another version")

dump_path = work_dir / "selected.dump"
client.download_file(
    bucket,
    dump_key,
    str(dump_path),
    ExtraArgs={"VersionId": dump_version},
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
if dump_head.get("ContentLength") != manifest["artifact"]["size_bytes"]:
    raise RuntimeError("dump remote size does not match manifest")
if dump_path.stat().st_size != manifest["artifact"]["size_bytes"]:
    raise RuntimeError("downloaded dump size does not match manifest")
for key, version in (
    (manifest_key, manifest_version),
    (dump_key, dump_version),
):
    retention = client.get_object_retention(
        Bucket=bucket,
        Key=key,
        VersionId=version,
    ).get("Retention", {})
    if retention.get("Mode") != "GOVERNANCE":
        raise RuntimeError(
            f"{key} has no GOVERNANCE retention"
        )
print("RESTORE_DOWNLOAD_VERIFICATION=PASS")
PY
# New manifests carry exact hardened PostgreSQL provenance. Legacy manifests
# retain the explicit pinned PostgreSQL 18 compatibility path below.
PG_IMAGE="$(python3 - "$WORK_DIR/selected.manifest.json" "$PG_IMAGE" <<'PYPG'
import json
import re
import subprocess
import sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
postgres = manifest["runtime"].get("postgres")
if postgres is None:
    print("Legacy manifest: exact PostgreSQL image identity unavailable", file=sys.stderr)
    print(sys.argv[2])
else:
    image_id = postgres["image_id"]
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise RuntimeError("invalid PostgreSQL image identity")
    image = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", image_id], text=True
    ))[0]
    if image["Config"]["Labels"].get("org.opencontainers.image.revision") != postgres["source_revision"]:
        raise RuntimeError("PostgreSQL image revision mismatch")
    print(image_id)
PYPG
)"
docker run --rm \
  --network none \
  -v "$WORK_DIR:/restore:ro" \
  "$PG_IMAGE" \
  pg_restore --list /restore/selected.dump \
  >/dev/null
echo "PG_RESTORE_LIST=PASS"
docker network create --internal "$RESTORE_NET"
RESTORE_NET_CREATED=true
docker volume create "$RESTORE_VOL"
RESTORE_VOL_CREATED=true
printf 'POSTGRES_PASSWORD=%s\n' "$RESTORE_PASSWORD" > "$WORK_DIR/postgres.env"
docker create \
  --name "$RESTORE_PG" \
  --network "$RESTORE_NET" \
  -e POSTGRES_DB=dc_inventory_restore \
  -e POSTGRES_USER=dc_inventory_restore \
  --env-file "$WORK_DIR/postgres.env" \
  -v "$RESTORE_VOL:/var/lib/postgresql" \
  -v "$WORK_DIR:/restore:ro" \
  "$PG_IMAGE" \
  >/dev/null
RESTORE_PG_CREATED=true
docker start "$RESTORE_PG" >/dev/null
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
  psql -U dc_inventory_restore -d dc_inventory_restore \
  -v ON_ERROR_STOP=1 \
  -c "UPDATE auth_sessions SET revoked_at = GREATEST(now(), created_at) WHERE revoked_at IS NULL;" \
  >/dev/null
ACTIVE_RESTORED_SESSIONS="$(
  docker exec "$RESTORE_PG" \
    psql -U dc_inventory_restore -d dc_inventory_restore \
    -v ON_ERROR_STOP=1 -At \
    -c "SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL;"
)"
test "$ACTIVE_RESTORED_SESSIONS" = 0
echo "RESTORE_AUTH_SESSIONS_INVALIDATED=PASS"
RESTORED_ALEMBIC_HEAD="$(
    docker exec "$RESTORE_PG" \
      psql \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      -v ON_ERROR_STOP=1 \
      -At \
      -c 'SELECT version_num FROM alembic_version;' \
      | tr -d '[:space:]'
)"

EXPECTED_ALEMBIC_HEAD="$(
    python3 -c '
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
print(manifest["alembic_head"])
' "$WORK_DIR/selected.manifest.json"
)"

test -n "$RESTORED_ALEMBIC_HEAD"
test -n "$EXPECTED_ALEMBIC_HEAD"
test "$RESTORED_ALEMBIC_HEAD" = "$EXPECTED_ALEMBIC_HEAD"

echo "RESTORE_ALEMBIC=PASS"
echo "RESTORED_ALEMBIC_HEAD=$RESTORED_ALEMBIC_HEAD"

docker exec "$RESTORE_PG" \
  psql \
  -U dc_inventory_restore \
  -d dc_inventory_restore \
  -v ON_ERROR_STOP=1 \
  -At \
  -c "
    SELECT 'items=' || count(*) FROM items;
    SELECT 'stock_balances=' || count(*) FROM stock_balances;
    SELECT 'movements=' || count(*) FROM movements;
    SELECT 'movement_lines=' || count(*) FROM movement_lines;
  "
RUNTIME_ARTIFACTS="$(
  python3 - "$WORK_DIR/selected.manifest.json" "$ROOT" <<'PYARTIFACTS'
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[2]) / "ops/recovery"))
from validate_manifest import application_artifacts

manifest = json.loads(Path(sys.argv[1]).read_text())
backend, web = application_artifacts(manifest)
print(backend["image_id"], web["image_id"],
      backend["source_revision"], web["source_revision"])
PYARTIFACTS
)"
read -r BACKEND_IMAGE_ID WEB_IMAGE_ID BACKEND_REVISION WEB_REVISION <<< "$RUNTIME_ARTIFACTS"

docker image inspect "$BACKEND_IMAGE_ID" >/dev/null
docker image inspect "$WEB_IMAGE_ID" >/dev/null

python3 - "$WORK_DIR/selected.manifest.json" <<'PYEMAIL'
import json
import re
import subprocess
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
email = manifest["runtime"].get("email_worker")
if email is None:
    print("RESTORE_EMAIL_RUNTIME=LEGACY_MANIFEST")
elif email.get("state") == "disabled":
    if set(email) != {"state"}:
        raise RuntimeError("disabled email runtime has unexpected metadata")
    print("RESTORE_EMAIL_RUNTIME=DISABLED")
elif email.get("state") == "enabled":
    image_id = email.get("image_id", "")
    revision = email.get("source_revision", "")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise RuntimeError("invalid email worker image identity")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise RuntimeError("invalid email worker source revision")
    image = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", image_id], text=True
    ))[0]
    if image["Config"]["Labels"].get("org.opencontainers.image.revision") != revision:
        raise RuntimeError("email worker image revision mismatch")
    print("RESTORE_EMAIL_RUNTIME=ENABLED")
else:
    raise RuntimeError("invalid email worker runtime state")
PYEMAIL

test "$(
    docker image inspect \
      -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
      "$BACKEND_IMAGE_ID"
)" = "$BACKEND_REVISION"
test "$(
    docker image inspect \
      -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
      "$WEB_IMAGE_ID"
)" = "$WEB_REVISION"

echo "EXACT_RUNTIME_ARTIFACTS_LOCAL=PASS"

# Reconciliation must match the schema that produced the selected backup.
# Never use the current checkout's SQL here: production may be restoring an
# older, still-valid Alembic head.
RECONCILE_SQL="$WORK_DIR/reconcile_inventory_projections.sql"

docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --entrypoint cat \
  "$BACKEND_IMAGE_ID" \
  /app/scripts/reconcile_inventory_projections.sql \
  > "$RECONCILE_SQL"

test -s "$RECONCILE_SQL"

echo "RESTORE_RECONCILIATION_SOURCE=BACKEND_IMAGE"
echo "RESTORE_RECONCILIATION_SOURCE_REVISION=$BACKEND_REVISION"

docker cp \
  "$RECONCILE_SQL" \
  "$RESTORE_PG:/tmp/reconcile_inventory_projections.sql"

RECONCILE_OUTPUT="$(
    docker exec "$RESTORE_PG" \
      psql \
      -U dc_inventory_restore \
      -d dc_inventory_restore \
      -v ON_ERROR_STOP=1 \
      -At \
      -f /tmp/reconcile_inventory_projections.sql
)"

if [ -n "$(
    printf '%s' "$RECONCILE_OUTPUT" |
      tr -d '[:space:]'
)" ]; then
    echo "[FATAL] restored database projection drift detected" >&2
    printf '%s\n' "$RECONCILE_OUTPUT" >&2
    exit 1
fi

echo "RESTORE_RECONCILIATION=ZERO_DRIFT"

printf 'DATABASE_URL=postgresql+asyncpg://dc_inventory_restore:%s@%s:5432/dc_inventory_restore\n' \
  "$RESTORE_PASSWORD" "$RESTORE_PG" > "$WORK_DIR/application.env"
docker create \
  --name "$RESTORE_APP" \
  --network "$RESTORE_NET" \
  --read-only \
  --tmpfs /tmp \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --init \
  -e APP_ENV=production \
  -e TELEGRAM_BOT_TOKEN=restore-rehearsal-placeholder \
  -e ADMIN_TELEGRAM_USER_ID=1 \
  -e NOTIFICATION_TELEGRAM_USER_ID=2 \
  -e TELEGRAM_WEBHOOK_SECRET=restore-rehearsal-placeholder \
  -e TELEGRAM_WEB_APP_URL=https://app.spik-inventory.ru \
  --env-file "$WORK_DIR/application.env" \
  -e REAL_INVENTORY_MUTATIONS_ENABLED=false \
  "$BACKEND_IMAGE_ID" \
  >/dev/null
RESTORE_APP_CREATED=true
docker start "$RESTORE_APP" >/dev/null

for attempt in $(seq 1 60); do
    if docker exec "$RESTORE_APP" \
      python -c \
      "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=2).read()" \
      >/dev/null 2>&1; then
        break
    fi

    sleep 1
done

docker exec "$RESTORE_APP" \
  python -c \
  "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=2)); assert d.get('status') == 'ready'"

docker inspect \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  "$RESTORE_APP" \
  | grep -qx 'REAL_INVENTORY_MUTATIONS_ENABLED=false'

echo "RESTORE_RUNTIME_CONFIG=ISOLATED_PLACEHOLDERS"
echo "RESTORE_APP_COMPATIBILITY=PASS"

cleanup_runtime
trap - EXIT

test -z "$(
    docker ps -aq --filter "name=^/${RESTORE_APP}$"
)"

test -z "$(
    docker ps -aq --filter "name=^/${RESTORE_PG}$"
)"

! docker volume inspect "$RESTORE_VOL" >/dev/null 2>&1
! docker network inspect "$RESTORE_NET" >/dev/null 2>&1
test ! -e "$WORK_DIR"

test "$(production_id backend)" = "$PROD_BACKEND_BEFORE"
test "$(production_id web)" = "$PROD_WEB_BEFORE"
test "$(production_id telegram-worker)" = "$PROD_TELEGRAM_BEFORE"
test "$(production_id maintenance-worker)" = "$PROD_MAINTENANCE_BEFORE"
if [ "$PROD_EMAIL_ENABLED" = true ]; then
    test "$(production_id email-worker)" = "$PROD_EMAIL_BEFORE"
else
    test -z "$(docker compose ps -q email-worker)"
fi
test "$(production_id postgres)" = "$PROD_POSTGRES_BEFORE"

production_health

echo "ISOLATED_RESTORE_CLEANUP=PASS"
echo "PRODUCTION_RUNTIME_UNCHANGED=PASS"
echo "REAL_INVENTORY_MUTATIONS_ENABLED=false"
echo "INITIAL_PRODUCTION_BOOTSTRAP=COMPLETED"
echo "REGULAR_MUTATION_GATE=DISABLED"
echo "AUD_06_REHEARSAL=PASS"
