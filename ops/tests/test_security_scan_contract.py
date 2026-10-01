#!/usr/bin/env python3

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github/workflows/ci.yml").read_text()
BACKEND_DOCKERFILE = (ROOT / "backend/Dockerfile").read_text()
POSTGRES_DOCKERFILE = (ROOT / "ops/postgres/Dockerfile").read_text()
WEB_DOCKERFILE = (ROOT / "frontend/Dockerfile").read_text()

TRIVY_ACTION = (
    "aquasecurity/trivy-action@"
    "ed142fd0673e97e23eac54620cfb913e5ce36c25"
)


def pinned_arg(text: str, name: str) -> str:
    match = re.search(
        rf"^ARG {re.escape(name)}=([^\\s]+)$",
        text,
        flags=re.MULTILINE,
    )
    assert match is not None, name
    value = match.group(1)
    assert value
    assert "*" not in value
    assert "${" not in value
    return value


assert CI.count(TRIVY_ACTION) == 4
assert CI.count("version: v0.74.0") == 4
assert CI.count("severity: HIGH,CRITICAL") == 4
assert "severity: CRITICAL\\n" not in CI
assert CI.count('exit-code: "1"') == 4
assert CI.count("scanners: vuln") == 4
assert CI.count('ignore-unfixed: "true"') == 3
assert CI.count('ignore-unfixed: "false"') == 1
assert "trivyignores:" not in CI
assert not (ROOT / "ops/security/trivy-postgres.ignore.yaml").exists()

assert "scan-type: fs" in CI
assert "scan-ref: ." in CI

for image in (
    "dc-inventory-backend:local",
    "dc-inventory-web:local",
    "dc-inventory-postgres:local",
):
    assert f"image-ref: {image}" in CI, image

assert re.search(
    r"^ARG POSTGRES_IMAGE=postgres:18@sha256:[0-9a-f]{64}$",
    POSTGRES_DOCKERFILE,
    flags=re.MULTILINE,
)
assert re.search(
    r"^ARG GO_IMAGE=golang@sha256:[0-9a-f]{64}$",
    POSTGRES_DOCKERFILE,
    flags=re.MULTILINE,
)

gosu_commit = pinned_arg(POSTGRES_DOCKERFILE, "GOSU_COMMIT")
assert re.fullmatch(r"[0-9a-f]{40}", gosu_commit)

openssl_version = pinned_arg(POSTGRES_DOCKERFILE, "OPENSSL_VERSION")
postgres_pcre2_version = pinned_arg(POSTGRES_DOCKERFILE, "PCRE2_VERSION")
assert re.fullmatch(r"\\d+\\.\\d+\\.\\d+-[^\\s]+", openssl_version)
assert re.fullmatch(r"\\d+\\.\\d+-[^\\s]+", postgres_pcre2_version)

for package in (
    "openssl",
    "libssl3t64",
    "openssl-provider-legacy",
):
    assert f'"{package}=${{OPENSSL_VERSION}}"' in POSTGRES_DOCKERFILE

assert '"libpcre2-8-0=${PCRE2_VERSION}"' in POSTGRES_DOCKERFILE
assert "CGO_ENABLED=0 go build" in POSTGRES_DOCKERFILE
assert 'test "$(git rev-parse HEAD)" = "${GOSU_COMMIT}"' in POSTGRES_DOCKERFILE
assert "gosu nobody true" in POSTGRES_DOCKERFILE

backend_pcre2_version = pinned_arg(BACKEND_DOCKERFILE, "PCRE2_VERSION")
assert re.fullmatch(r"\\d+\\.\\d+-[^\\s]+", backend_pcre2_version)
assert '"libpcre2-8-0=${PCRE2_VERSION}"' in BACKEND_DOCKERFILE
assert "apt-get update" in BACKEND_DOCKERFILE
assert "rm -rf /var/lib/apt/lists/*" in BACKEND_DOCKERFILE

assert re.search(r"libexpat=[^\\s\\\\]+", WEB_DOCKERFILE)
assert re.search(r"libuuid=[^\\s\\\\]+", WEB_DOCKERFILE)
assert "apk add --no-cache --upgrade" in WEB_DOCKERFILE

action_refs = re.findall(
    r"^\\s+- uses:\\s+([^@\\s]+)@([^\\s#]+)",
    CI,
    flags=re.MULTILINE,
)

for name, ref in action_refs:
    assert re.fullmatch(r"[0-9a-f]{40}", ref), (name, ref)

assert 'cron: "23 4 * * 1"' in CI
assert "  workflow_dispatch:" in CI

print("SECURITY_SCANNER_PINNING=PASS")
print("HIGH_CRITICAL_VULNERABILITY_GATES=PASS")
print("HARDENED_RUNTIME_IMAGES=PASS")
