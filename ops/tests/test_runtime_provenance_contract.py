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
ci = (ROOT / ".github/workflows/ci.yml").read_text()

compile(
    provenance,
    str(provenance_path),
    "exec",
)

assert "source_checkout_sha" not in backup
assert '"schema_version": 2' in backup
assert '"production_checkout_sha"' in backup
assert "verify_checkout(args.root, checkout)" in provenance
assert '"runtime": provenance["runtime"]' in backup
assert "runtime-provenance.json" in backup

for service in (
    '"backend"',
    '"telegram_worker"',
    '"maintenance_worker"',
    '"email_worker"',
    '"web"',
    '"postgres"',
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
assert "email-worker runtime does not match backend runtime" in provenance
assert '"state": "disabled"' in provenance
assert "EMAIL_DELIVERY_ENABLED" in provenance

# CI must distinguish running image-backed services from a profile-gated
# disabled email worker. Blindly requiring image provenance for every
# runtime entry regresses when email delivery is intentionally disabled.
assert 'for runtime in data["runtime"].values()' not in ci

for service in (
    '"backend"',
    '"telegram_worker"',
    '"maintenance_worker"',
    '"web"',
    '"postgres"',
):
    assert service in ci

assert 'runtime["email_worker"]' in ci
assert '"state": "disabled"' in ci
assert 'runtime[service]["source_revision"]' in ci
assert 'runtime[service]["image_id"]' in ci

label = "org.opencontainers.image.revision"

assert label in backend
assert label in frontend

for dockerfile in (backend, frontend, (ROOT / "ops/postgres/Dockerfile").read_text()):
    assert "ARG APP_REVISION\n" in dockerfile
    assert 'test -n "$APP_REVISION"' in dockerfile
    assert 'test "$APP_REVISION" != "unknown"' in dockerfile
    assert "APP_REVISION=unknown" not in dockerfile

assert (
    compose.count(
        "APP_REVISION: ${APP_REVISION:-}"
    )
    == 3
)
assert "APP_REVISION:-unknown" not in compose

assert (
    compose_dev.count(
        "APP_REVISION: ${APP_REVISION:-development}"
    )
    == 2
)
assert "APP_REVISION:-unknown" not in compose_dev

print("AUD_02_SOURCE_CONTRACT=PASS")

assert '["docker", "image", "inspect", image_id]' in provenance
recovery = (ROOT / "ops/recovery/rehearse_restore.sh").read_text()
assert 'manifest["runtime"].get("postgres")' in recovery
assert "PostgreSQL image revision mismatch" in recovery
assert 'manifest["runtime"].get("email_worker")' in recovery
assert "RESTORE_EMAIL_RUNTIME=LEGACY_MANIFEST" in recovery
assert "RESTORE_EMAIL_RUNTIME=DISABLED" in recovery
assert "RESTORE_EMAIL_RUNTIME=ENABLED" in recovery
