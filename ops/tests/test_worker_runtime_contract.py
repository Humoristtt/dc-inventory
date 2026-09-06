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

for service, limit in expected_pids.items():
    block = service_block(service)
    assert "logging: *runtime-logging" in block, service
    assert f"pids_limit: {limit}" in block, service

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

for filename in (
    "backend/app/modules/notifications/worker.py",
    "backend/app/maintenance/worker.py",
):
    source = (ROOT / filename).read_text()

    assert (
        "from app.core.worker_health import heartbeat_forever"
        in source
    ), filename

    assert "asyncio.TaskGroup()" in source, filename
    assert "heartbeat_forever()" in source, filename

health_source = (
    ROOT / "backend/app/core/worker_health.py"
).read_text()

assert "heartbeat_is_fresh" in health_source
assert "os.utime" in health_source

print("WORKER_HEALTH_CONTRACT=PASS")
print("DOCKER_RUNTIME_POLICY_CONTRACT=PASS")
print("AUD15_16_CONTRACT=PASS")
