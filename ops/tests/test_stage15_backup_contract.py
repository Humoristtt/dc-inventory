#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

BACKUP = ROOT / "ops/backup/dc-inventory-backup-s3"
HELPER = ROOT / "ops/backup/s3_stage15.py"
SERVICE = ROOT / "ops/systemd/dc-inventory-backup-s3.service"
TIMER = ROOT / "ops/systemd/dc-inventory-backup-s3.timer"


def require(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise RuntimeError(f"{label}: missing {needle!r}")


for path in (BACKUP, HELPER, SERVICE, TIMER):
    if not path.is_file():
        raise RuntimeError(f"Missing Stage15A file: {path}")

backup = BACKUP.read_text()
helper = HELPER.read_text()
service = SERVICE.read_text()
timer = TIMER.read_text()

subprocess.run(
    ["bash", "-n", str(BACKUP)],
    check=True,
)

compile(
    helper,
    str(HELPER),
    "exec",
)

for needle, label in (
    ('set -Eeuo pipefail', "strict shell"),
    ('umask 077', "private artifacts"),
    ('if [ "${EUID}" -ne 0 ]', "root execution"),
    ('--format=custom', "custom pg_dump"),
    ('pg_restore --list', "archive validation"),
    ('sha256sum "${DB_FILE}"', "SHA-256"),
    ('last-success.json', "success state"),
    ('last-failure.json', "failure state"),
    ('docker compose ps -q postgres', "existing PostgreSQL container"),
    ('safe.directory="${ROOT_DIR}"', "root Git safety"),
    ('STAGE15A_BACKUP=PASS', "success marker"),
):
    require(backup, needle, label)

for needle, label in (
    ('get_object_lock_configuration', "Object Lock preflight"),
    ('get_bucket_lifecycle_configuration', "lifecycle preflight"),
    ('get_object_retention', "remote retention verification"),
    ('head_object', "remote metadata verification"),
    ('get_object(', "remote content verification"),
    ('downloaded_sha256', "remote SHA-256 verification"),
    ('"Metadata": {', "remote checksum metadata"),
    ('"sha256": sha256', "SHA-256 upload metadata"),
    ('S3_OBJECT_LOCK=GOVERNANCE_7D_PASS', "Object Lock marker"),
    ('S3_RETENTION_30D=PASS', "retention marker"),
    ('STAGE15A_REMOTE_VERIFICATION=PASS', "remote verification marker"),
):
    require(helper, needle, label)

for forbidden in (
    "delete_object(",
    "put_bucket_lifecycle_configuration(",
    "BypassGovernanceRetention",
):
    if forbidden in helper:
        raise RuntimeError(
            f"S3 helper contains forbidden privilege/action: {forbidden}"
        )

for source_name, source in (
    ("backup", backup),
    ("helper", helper),
):
    hardcoded_secret = re.search(
        r'(?im)^\s*S3_(?:ACCESS_KEY|SECRET_KEY)\s*='
        r'\s*["\'][^"$\']+["\']',
        source,
    )
    if hardcoded_secret:
        raise RuntimeError(
            f"{source_name}: possible hardcoded S3 credential"
        )

for needle, label in (
    ('User=root', "systemd root execution"),
    (
        'ExecStart=/opt/dc-inventory/ops/backup/'
        'dc-inventory-backup-s3',
        "systemd ExecStart",
    ),
    ('PrivateTmp=true', "systemd private tmp"),
    ('ProtectSystem=full', "systemd filesystem protection"),
    ('NoNewPrivileges=true', "systemd privilege protection"),
):
    require(service, needle, label)

for needle, label in (
    (
        'OnCalendar=*-*-* 02:30:00 Europe/Moscow',
        "daily 02:30 MSK schedule",
    ),
    ('Persistent=true', "missed-run catchup"),
    ('RandomizedDelaySec=0', "deterministic schedule"),
    (
        'Unit=dc-inventory-backup-s3.service',
        "timer service target",
    ),
):
    require(timer, needle, label)

if "5432:" in backup or "-p 5432" in backup:
    raise RuntimeError("Backup must not publish PostgreSQL host port")

print("STAGE15A_CONTRACT_TEST=PASS")
