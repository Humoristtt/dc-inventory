#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

backup = (
    ROOT / "ops/backup/dc-inventory-backup-s3"
).read_text()

provenance_path = (
    ROOT / "ops/backup/runtime_provenance.py"
)
provenance = provenance_path.read_text()

backend = (ROOT / "backend/Dockerfile").read_text()
frontend = (ROOT / "frontend/Dockerfile").read_text()
compose = (ROOT / "compose.yaml").read_text()
compose_dev = (ROOT / "compose.dev.yaml").read_text()

compile(
    provenance,
    str(provenance_path),
    "exec",
)

assert "source_checkout_sha" not in backup
assert '"schema_version": 2' in backup
assert '"production_checkout_sha"' in backup
assert '"runtime": provenance["runtime"]' in backup
assert "runtime-provenance.json" in backup

for service in (
    '"backend"',
    '"telegram_worker"',
    '"maintenance_worker"',
    '"web"',
):
    assert service in provenance

assert (
    "telegram-worker runtime does not match backend runtime"
    in provenance
)
assert (
    "maintenance-worker runtime does not match backend runtime"
    in provenance
)

label = "org.opencontainers.image.revision"

assert label in backend
assert label in frontend

for source in (compose, compose_dev):
    assert (
        source.count(
            "APP_REVISION: ${APP_REVISION:-unknown}"
        )
        == 2
    )

print("AUD_02_SOURCE_CONTRACT=PASS")
