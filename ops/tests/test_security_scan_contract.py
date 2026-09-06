#!/usr/bin/env python3

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github/workflows/ci.yml").read_text()

TRIVY_ACTION = (
    "aquasecurity/trivy-action@"
    "ed142fd0673e97e23eac54620cfb913e5ce36c25"
)

assert CI.count(TRIVY_ACTION) == 4
assert CI.count("version: v0.74.0") == 4
assert CI.count("severity: CRITICAL") == 4
assert CI.count('exit-code: "1"') == 4
assert CI.count("scanners: vuln") == 4
assert CI.count('ignore-unfixed: "true"') == 3
assert CI.count('ignore-unfixed: "false"') == 1
assert CI.count(
    "trivyignores: ops/security/trivy-postgres.ignore.yaml"
) == 1

POSTGRES_IGNORE = (
    ROOT / "ops/security/trivy-postgres.ignore.yaml"
).read_text()

assert "CVE-2025-68121" in POSTGRES_IGNORE
assert '      - "usr/local/bin/gosu"' in POSTGRES_IGNORE
assert "expired_at: 2026-10-07" in POSTGRES_IGNORE

postgres_marker = (
    "      - name: Scan PostgreSQL image for critical vulnerabilities\n"
)
postgres_start = CI.index(postgres_marker)
postgres_end = CI.find(
    "\n      - name:",
    postgres_start + len(postgres_marker),
)
if postgres_end == -1:
    postgres_end = len(CI)

postgres_block = CI[postgres_start:postgres_end]

assert (
    "trivyignores: ops/security/trivy-postgres.ignore.yaml"
    in postgres_block
)

assert "trivyignores:" not in CI[:postgres_start]

assert "scan-type: fs" in CI
assert "scan-ref: ." in CI

required_images = (
    "dc-inventory-backend:local",
    "dc-inventory-web:local",
    (
        "postgres:18@sha256:"
        "4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"
    ),
)

for image in required_images:
    assert f"image-ref: {image}" in CI, image

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
print("CRITICAL_VULNERABILITY_GATE=PASS")
print("AUD14_SECURITY_SCAN_CONTRACT=PASS")
