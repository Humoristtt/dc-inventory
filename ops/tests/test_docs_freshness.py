#!/usr/bin/env python3
"""Current-state documentation freshness contract."""

from __future__ import annotations

from pathlib import Path

from alembic_graph import single_source_alembic_head

ROOT = Path(__file__).resolve().parents[2]

CURRENT_DOCS = (
    "README.md",
    "docs/README.md",
    "docs/CURRENT_STATE_AUDIT.md",
    "docs/ARCHITECTURE.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/ACCESS_AND_RBAC.md",
    "docs/CATALOG.md",
    "docs/WAREHOUSE.md",
    "docs/PROCUREMENT.md",
    "docs/NOTIFICATIONS.md",
    "docs/FRONTEND.md",
    "docs/SECURITY.md",
    "docs/DEVELOPMENT.md",
    "docs/DEPLOYMENT.md",
    "docs/OPERATIONS.md",
    "docs/RECOVERY_RUNBOOK.md",
)

LEGACY_NAMES = (
    "AUDIT_0_12_REMEDIATION.md",
    "CATALOG_SCHEMA.md",
    "CATALOG_SOURCE_REFERENCE.md",
    "CP07_HTTP_SOCKET_MIGRATION.md",
    "CP13_DOCUMENTATION_AUDIT.md",
    "FRONTEND_DESIGN_SYSTEM.md",
    "FRONTEND_PERFORMANCE.md",
    "HISTORY.md",
    "MASTER_REMEDIATION_PLAN.md",
    "RBAC_PROCUREMENT.md",
    "ROADMAP.md",
    "STAGE15_AUDIT_REMEDIATION.md",
    "STAGE15_PLAN.md",
    "WAREHOUSE_DOMAIN.md",
)

texts: dict[str, str] = {}

for name in CURRENT_DOCS:
    path = ROOT / name
    assert path.is_file(), f"missing current-state document: {name}"
    texts[name] = path.read_text(encoding="utf-8")

combined = "\n".join(texts.values())

for legacy in LEGACY_NAMES:
    assert legacy not in combined, f"stale legacy document reference: {legacy}"

head = single_source_alembic_head()
assert f"ALEMBIC_HEAD={head}" in texts["README.md"]
assert f"Alembic source head: `{head}`" in texts[
    "docs/CURRENT_STATE_AUDIT.md"
]

for required in (
    "source+CI evidence",
    "live production",
    "P0/P1",
    "F-02",
    "F-03",
    "F-04",
    "F-05",
):
    assert required.lower() in texts[
        "docs/CURRENT_STATE_AUDIT.md"
    ].lower(), required

for name in (
    "README.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/WAREHOUSE.md",
    "docs/DEPLOYMENT.md",
):
    assert "REAL_INVENTORY_MUTATIONS_ENABLED=false" in texts[name], name

for name in (
    "README.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/NOTIFICATIONS.md",
    "docs/DEPLOYMENT.md",
):
    assert "EMAIL_DELIVERY_ENABLED=false" in texts[name], name

assert "UserItemCustodyBalance" in texts["README.md"]
assert "UserItemCustodyBalance" in texts["docs/WAREHOUSE.md"]
assert "identity_signature" in texts["docs/CATALOG.md"]
assert "state_version" in texts["docs/PROCUREMENT.md"]
assert "at-least-once" in texts["docs/NOTIFICATIONS.md"]
assert "exactly-once" in texts["docs/NOTIFICATIONS.md"].lower()
assert "production cutover" in texts["docs/RECOVERY_RUNBOOK.md"].lower()
assert "RELEASE_RUNTIME_MATCH=PASS" in texts["docs/DEPLOYMENT.md"]
assert "REPOSITORY_VISIBILITY_CURRENT=public" in texts["docs/OPERATIONS.md"]

# Old accepted baselines must not masquerade as current production state.
for stale in (
    "593ddec0c9100b0df2eafe4f324c7bb600d75cba",
    "b0c1d2e3f4a5",
    "CP-16 production deployment",
    "CP-17 real Telegram",
):
    assert stale not in combined, stale

print(f"DOCS_FRESHNESS=PASS alembic_head={head}")
