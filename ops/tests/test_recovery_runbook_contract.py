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
    "RESTORE_MANIFEST_CHECKOUT_METADATA=PASS",
    "RESTORE_ALEMBIC=PASS",
    "RESTORE_RECONCILIATION=ZERO_DRIFT",
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
):
    assert forbidden not in source, forbidden

assert "ops/recovery/rehearse_restore.sh" in doc
assert "production cutover" in doc.lower()

print("AUD_06_RECOVERY_RUNBOOK_CONTRACT=PASS")
