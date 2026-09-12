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

POSTGRES_BASE_DIGEST = (
    "4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"
)
GO_DIGEST = (
    "e8c859f5632dcfde7b32d2012b4351728f6437930887c2f6a91ea242459e5514"
)
GOSU_COMMIT = "6456aaa0f3c854d199d0f037f068eb97515b7513"

assert CI.count(TRIVY_ACTION) == 4
assert CI.count("version: v0.74.0") == 4
assert CI.count("severity: HIGH,CRITICAL") == 4
assert "severity: CRITICAL\n" not in CI
assert CI.count('exit-code: "1"') == 4
assert CI.count("scanners: vuln") == 4
assert CI.count('ignore-unfixed: "true"') == 3
assert CI.count('ignore-unfixed: "false"') == 1
assert "trivyignores:" not in CI
assert not (ROOT / "ops/security/trivy-postgres.ignore.yaml").exists()

assert "scan-type: fs" in CI
assert "scan-ref: ." in CI

required_images = (
    "dc-inventory-backend:local",
    "dc-inventory-web:local",
    "dc-inventory-postgres:local",
)

for image in required_images:
    assert f"image-ref: {image}" in CI, image

assert (
    f"ARG POSTGRES_IMAGE=postgres:18@sha256:{POSTGRES_BASE_DIGEST}"
    in POSTGRES_DOCKERFILE
)
assert (
    f"ARG GO_IMAGE=golang@sha256:{GO_DIGEST}"
    in POSTGRES_DOCKERFILE
)
assert f"ARG GOSU_COMMIT={GOSU_COMMIT}" in POSTGRES_DOCKERFILE
assert "ARG OPENSSL_VERSION=3.5.7-1~deb13u2" in POSTGRES_DOCKERFILE
assert '"openssl=${OPENSSL_VERSION}"' in POSTGRES_DOCKERFILE
assert '"libssl3t64=${OPENSSL_VERSION}"' in POSTGRES_DOCKERFILE
assert '"openssl-provider-legacy=${OPENSSL_VERSION}"' in POSTGRES_DOCKERFILE
assert "CGO_ENABLED=0 go build" in POSTGRES_DOCKERFILE
assert "test \"$(git rev-parse HEAD)\" = \"${GOSU_COMMIT}\"" in POSTGRES_DOCKERFILE
assert "openssl-provider-legacy" in POSTGRES_DOCKERFILE
assert "gosu nobody true" in POSTGRES_DOCKERFILE

assert "ARG PCRE2_VERSION=10.42-1+deb12u1" in BACKEND_DOCKERFILE
assert '"libpcre2-8-0=${PCRE2_VERSION}"' in BACKEND_DOCKERFILE
assert "apt-get update" in BACKEND_DOCKERFILE
assert "rm -rf /var/lib/apt/lists/*" in BACKEND_DOCKERFILE

assert "apk add --no-cache --upgrade libuuid=2.42.3-r1" in WEB_DOCKERFILE

action_refs = re.findall(
    r"^\s+- uses:\s+([^@\s]+)@([^\s#]+)",
    CI,
    flags=re.MULTILINE,
)

for name, ref in action_refs:
    assert re.fullmatch(r"[0-9a-f]{40}", ref), (
        name,
        ref,
    )

print("SECURITY_SCANNER_PINNING=PASS")
print("HIGH_CRITICAL_VULNERABILITY_GATES=PASS")
print("HARDENED_RUNTIME_IMAGES=PASS")
print("AUD14_SECURITY_SCAN_CONTRACT=PASS")

assert 'cron: "23 4 * * 1"' in CI
assert "  workflow_dispatch:" in CI
