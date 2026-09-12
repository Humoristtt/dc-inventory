#!/usr/bin/env python3

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"

text = COMPOSE.read_text()


def service_block(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n"
        rf"(?P<body>.*?)"
        rf"(?=^  [a-z0-9-]+:\n|^volumes:\n)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise AssertionError(f"service missing: {name}")
    return match.group("body")


assert "x-runtime-logging: &runtime-logging" in text
assert 'driver: local' in text
assert 'max-size: "20m"' in text
assert 'max-file: "5"' in text

expected_pids = {
    "postgres": 512,
    "migrate": 256,
    "db-permissions": 256,
    "backend": 256,
    "telegram-worker": 256,
    "maintenance-worker": 256,
    "web": 256,
}

expected_resources = {
    "postgres": (
        "${POSTGRES_CPUS_LIMIT:-2.0}",
        "${POSTGRES_MEMORY_LIMIT:-3g}",
    ),
    "migrate": (
        "${MIGRATE_CPUS_LIMIT:-1.0}",
        "${MIGRATE_MEMORY_LIMIT:-512m}",
    ),
    "db-permissions": (
        "${DB_PERMISSIONS_CPUS_LIMIT:-0.5}",
        "${DB_PERMISSIONS_MEMORY_LIMIT:-256m}",
    ),
    "backend": (
        "${BACKEND_CPUS_LIMIT:-1.5}",
        "${BACKEND_MEMORY_LIMIT:-1g}",
    ),
    "telegram-worker": (
        "${TELEGRAM_WORKER_CPUS_LIMIT:-0.5}",
        "${TELEGRAM_WORKER_MEMORY_LIMIT:-512m}",
    ),
    "maintenance-worker": (
        "${MAINTENANCE_WORKER_CPUS_LIMIT:-0.5}",
        "${MAINTENANCE_WORKER_MEMORY_LIMIT:-512m}",
    ),
    "web": (
        "${WEB_CPUS_LIMIT:-0.5}",
        "${WEB_MEMORY_LIMIT:-256m}",
    ),
}

for service, limit in expected_pids.items():
    block = service_block(service)
    assert "logging: *runtime-logging" in block, service
    assert f"pids_limit: {limit}" in block, service

for service, (cpus, memory) in expected_resources.items():
    block = service_block(service)
    assert f"cpus: {cpus}" in block, service
    assert f"mem_limit: {memory}" in block, service

for service in (
    "telegram-worker",
    "maintenance-worker",
):
    block = service_block(service)

    assert "healthcheck:" in block, service
    assert "app.core.worker_health" in block, service
    assert 'WORKER_HEARTBEAT_INTERVAL_SECONDS: "10"' in block
    assert 'WORKER_HEARTBEAT_MAX_AGE_SECONDS: "60"' in block
    assert "interval: 15s" in block
    assert "timeout: 3s" in block
    assert "retries: 3" in block
    assert "start_period: 20s" in block

notification_source = (
    ROOT / "backend/app/modules/notifications/worker.py"
).read_text()

assert "write_worker_heartbeat" in notification_source
assert "heartbeat_forever" not in notification_source
assert "Notification worker iteration failed" in notification_source

maintenance_source = (
    ROOT / "backend/app/maintenance/worker.py"
).read_text()

assert (
    "from app.core.worker_health import heartbeat_forever"
    in maintenance_source
)
assert "asyncio.TaskGroup()" in maintenance_source
assert "heartbeat_forever()" in maintenance_source

health_source = (
    ROOT / "backend/app/core/worker_health.py"
).read_text()

assert "heartbeat_is_fresh" in health_source
assert "write_worker_heartbeat" in health_source
assert "os.utime" in health_source

db_permissions = service_block("db-permissions")
assert "/var/lib/postgresql" in db_permissions

print("WORKER_HEALTH_CONTRACT=PASS")
print("DOCKER_RUNTIME_POLICY_CONTRACT=PASS")
print("AUD15_16_CONTRACT=PASS")

assert "  app_net:\n    internal: true" in text
assert "  db_net:\n    internal: true" in text
assert "- ingress_net" in service_block("web")
assert "- egress_net" in service_block("telegram-worker")
for service in ("backend", "postgres", "maintenance-worker", "migrate"):
    assert "- ingress_net" not in service_block(service)
    assert "- egress_net" not in service_block(service)
assert '- "127.0.0.1:${WEB_PORT:-8080}:8080"' in service_block("web")
