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

require(
    "docs/PRODUCT_REQUIREMENTS.md",
    "Stage15C final pre-data hardening активен",
)
forbid(
    "docs/PRODUCT_REQUIREMENTS.md",
    "Stage 8B реализован локально и ожидает",
)

require(
    "docs/DEVELOPMENT.md",
    "npx playwright install chromium webkit",
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
    "RESTORE_DOWNLOAD_VERIFICATION=PASS",
    "pg_restore --list",
    "docker network create --internal",
    "docker volume create",
    "ISOLATED_RESTORE=PASS",
    "reconcile_inventory_projections.sql",
    "docker image inspect",
    "docker rm -f",
    "docker volume rm",
    "docker network rm",
    "ISOLATED_RESTORE_CLEANUP=PASS",
    "## 11. Production cutover boundary",
):
    require(
        "docs/RECOVERY_RUNBOOK.md",
        assertion,
    )

print("DOCS_FRESHNESS_CONTRACT=PASS")
