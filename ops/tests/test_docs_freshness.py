#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def content(name: str) -> str:
    path = ROOT / name

    if not path.is_file():
        raise RuntimeError(f"missing current-state document: {name}")

    return path.read_text()


def require(name: str, value: str) -> None:
    if value not in content(name):
        raise RuntimeError(
            f"{name}: missing current-state assertion {value!r}"
        )


def forbid(name: str, value: str) -> None:
    if value in content(name):
        raise RuntimeError(
            f"{name}: stale current-state assertion {value!r}"
        )


require("README.md", "REAL_INVENTORY_MUTATIONS_ENABLED=false")
require("README.md", "Stage15B")

for stale_doc in (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/CATALOG_SCHEMA.md",
    "docs/CATALOG_SOURCE_REFERENCE.md",
    "docs/HISTORY.md",
    "docs/OPERATIONS.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "docs/STAGE15_PLAN.md",
    "docs/ROADMAP.md",
):
    for stale_value in (
        "sfp-authoritative",
        "authoritative workbook fingerprint",
        "Инвентаризация SFP модулей.xlsx",
    ):
        forbid(stale_doc, stale_value)

require(
    "docs/STAGE15_PLAN.md",
    "CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED",
)
require(
    "docs/STAGE15_PLAN.md",
    "REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP",
)

require(
    "docs/PRODUCT_REQUIREMENTS.md",
    "Stage15 technical hardening завершён",
)
forbid(
    "docs/PRODUCT_REQUIREMENTS.md",
    "Stage 8B реализован локально и ожидает",
)

require(
    "docs/DEVELOPMENT.md",
    "npx playwright install chromium webkit",
)
require(
    "docs/DEVELOPMENT.md",
    "frontend/e2e/warehouse-v2.spec.ts",
)
for stale_value in (
    "frontend/e2e/stage8.spec.ts",
    "latest serial state",
    "allocation и reactivation/reversal races",
):
    forbid(
        "docs/DEVELOPMENT.md",
        stale_value,
    )
forbid(
    "docs/DEVELOPMENT.md",
    "Production остаётся на `f1a2b3c4d5e6`",
)

require(
    "docs/ARCHITECTURE.md",
    "org.opencontainers.image.revision",
)
forbid(
    "docs/ARCHITECTURE.md",
    "Production migration head до Stage 8B release",
)

require(
    "docs/DEPLOYMENT.md",
    "docs/RECOVERY_RUNBOOK.md",
)
forbid(
    "docs/DEPLOYMENT.md",
    "Текущий accepted production source:",
)

require(
    "docs/OPERATIONS.md",
    "AUD-01 production acceptance",
)

require(
    "docs/STAGE15_PLAN.md",
    "AUD_01=PASS",
)

require(
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "- [x] AUD-01",
)

require(
    "docs/ROADMAP.md",
    "REAL_INVENTORY_MUTATIONS_ENABLED=false",
)

for assertion in (
    "## 10A. Guarded command-level rehearsal",
    "ops/recovery/rehearse_restore.sh",
    "sudo -n bash ops/recovery/rehearse_restore.sh",
    "## 11. Production cutover boundary",
):
    require(
        "docs/RECOVERY_RUNBOOK.md",
        assertion,
    )


current_gate_docs = (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/OPERATIONS.md",
    "docs/ROADMAP.md",
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "docs/STAGE15_PLAN.md",
    "docs/RECOVERY_RUNBOOK.md",
)

for name in current_gate_docs:
    require(
        name,
        "BLOCKED_PENDING_NEXT_ROADMAP",
    )
    forbid(
        name,
        "BLOCKED_STAGE15",
    )

forbid(
    "docs/DEVELOPMENT.md",
    "Stage15C acceptance",
)
require(
    "docs/DEVELOPMENT.md",
    "npm run test:e2e:fullstack",
)

require(
    "docs/STAGE15_PLAN.md",
    "STAGE15=TECHNICAL_HARDENING_COMPLETE",
)
require(
    "docs/STAGE15_PLAN.md",
    "STAGE15_GATE_DECISION=KEEP_DISABLED_NEXT_ROADMAP",
)
require(
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "- [x] AUD-24",
)
require(
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "BATCH_D=PASS",
)
require(
    "docs/ROADMAP.md",
    "Stage 15 technical hardening COMPLETE",
)
for name in (
    "README.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/DEPLOYMENT.md",
    "docs/ROADMAP.md",
    "docs/STAGE15_PLAN.md",
):
    forbid(name, "STAGE15=ACTIVE_15C")
    forbid(name, "Stage15C final pre-data hardening активен")

print("DOCS_FRESHNESS_CONTRACT=PASS")
