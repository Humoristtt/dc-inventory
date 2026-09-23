#!/usr/bin/env python3
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/recovery/rehearse_restore.sh"
DOC = ROOT / "docs/RECOVERY_RUNBOOK.md"

source = SCRIPT.read_text()
doc = DOC.read_text()

subprocess.run(
    ["bash", "-n", str(SCRIPT)],
    check=True,
)

for required in (
    "set -Eeuo pipefail",
    'if [ "${EUID}" -ne 0 ]',
    "RESTORE_DOWNLOAD_VERIFICATION=PASS",
    "validate_manifest(json.loads(manifest_path.read_text()), manifest_key, prefix)",
    'dump_head.get("ContentLength") != manifest["artifact"]["size_bytes"]',
    'dump_path.stat().st_size != manifest["artifact"]["size_bytes"]',
    "RESTORE_MANIFEST_CHECKOUT_METADATA=PASS",
    "RESTORE_ALEMBIC=PASS",
    "RESTORE_RECONCILIATION=ZERO_DRIFT",
    "RESTORE_RECONCILIATION_SOURCE=BACKEND_IMAGE",
    "RESTORE_RECONCILIATION_SOURCE_REVISION=",
    "backend, web = application_artifacts(manifest)",
    'python3 - "$WORK_DIR/selected.manifest.json" "$ROOT" <<\'PYARTIFACTS\'',
    'Path(sys.argv[2]) / "ops/recovery"',
    "read -r BACKEND_IMAGE_ID WEB_IMAGE_ID BACKEND_REVISION WEB_REVISION",
    "/app/scripts/reconcile_inventory_projections.sql",
    "--entrypoint cat",
    "EXACT_RUNTIME_ARTIFACTS_LOCAL=PASS",
    ')" = "$WEB_REVISION"',
    "RESTORE_EMAIL_RUNTIME=LEGACY_MANIFEST",
    "RESTORE_EMAIL_RUNTIME=DISABLED",
    "RESTORE_EMAIL_RUNTIME=ENABLED",
    "RESTORE_RUNTIME_CONFIG=ISOLATED_PLACEHOLDERS",
    "pg_restore --list",
    "docker network create --internal",
    "docker volume create",
    "ISOLATED_RESTORE=PASS",
    "reconcile_inventory_projections.sql",
    "RESTORE_APP_COMPATIBILITY=PASS",
    "REAL_INVENTORY_MUTATIONS_ENABLED=false",
    "INITIAL_PRODUCTION_BOOTSTRAP=COMPLETED",
    "REGULAR_MUTATION_GATE=DISABLED",
    "cleanup_runtime() (",
    "RESTORE_NET_CREATED=true",
    "RESTORE_VOL_CREATED=true",
    "RESTORE_PG_CREATED=true",
    "RESTORE_APP_CREATED=true",
    "docker rm -f",
    "docker volume rm",
    "docker network rm",
    "PRODUCTION_RUNTIME_UNCHANGED=PASS",
    "AUD_06_REHEARSAL=PASS",
):
    assert required in source, required

for forbidden in (
    "docker compose down -v",
    "BypassGovernanceRetention",
    "REAL_INVENTORY_MUTATIONS_ENABLED=true",
    "REAL_INVENTORY_ENTRY=BLOCKED_STAGE15",
    "REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP",
    "backup manifest does not match current production checkout",
    '$ROOT/backend/scripts/reconcile_inventory_projections.sql',
):
    assert forbidden not in source, forbidden

assert "ops/recovery/rehearse_restore.sh" in doc
assert "production cutover" in doc.lower()
assert "из manifest получить immutable backend/web image ids" in doc.lower()
assert "запустить точный доступный backend image" in doc.lower()
assert "/app/scripts/reconcile_inventory_projections.sql" in doc

for needle in (
    'VersionId=manifest_version',
    'VersionId=dump_version',
    'ExtraArgs={"VersionId": manifest_version}',
    'ExtraArgs={"VersionId": dump_version}',
    'state["dump_sha256"]',
    'manifest_dump_version != state_dump_version',
):
    assert needle in source, needle

print("AUD_06_RECOVERY_RUNBOOK_CONTRACT=PASS")
