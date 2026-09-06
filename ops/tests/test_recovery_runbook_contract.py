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
    "pg_restore --list",
    "docker network create --internal",
    "docker volume create",
    "ISOLATED_RESTORE=PASS",
    "reconcile_inventory_projections.sql",
    "RESTORE_APP_COMPATIBILITY=PASS",
    "REAL_INVENTORY_MUTATIONS_ENABLED=false",
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
):
    assert forbidden not in source, forbidden

assert "ops/recovery/rehearse_restore.sh" in doc
assert "production cutover" in doc.lower()

print("AUD_06_RECOVERY_RUNBOOK_CONTRACT=PASS")
