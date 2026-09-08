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


CURRENT_DOCS = (
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/CATALOG_SCHEMA.md",
    "docs/CATALOG_SOURCE_REFERENCE.md",
    "docs/DEPLOYMENT.md",
    "docs/DEVELOPMENT.md",
    "docs/OPERATIONS.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/RECOVERY_RUNBOOK.md",
    "docs/ROADMAP.md",
    "docs/WAREHOUSE_DOMAIN.md",
)

HISTORICAL_STAGE15_DOCS = (
    "docs/STAGE15_PLAN.md",
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "docs/HISTORY.md",
)


# ---------------------------------------------------------------------------
# Global source-data hygiene
# ---------------------------------------------------------------------------

for name in CURRENT_DOCS + HISTORICAL_STAGE15_DOCS:
    for forbidden_value in (
        "sfp-authoritative",
        "authoritative workbook fingerprint",
        "Инвентаризация SFP модулей.xlsx",
    ):
        forbid(name, forbidden_value)


# ---------------------------------------------------------------------------
# Current production baseline
# ---------------------------------------------------------------------------

for name in (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/DEVELOPMENT.md",
    "docs/OPERATIONS.md",
):
    require(name, "c5d6e7f8a9b0")

for name in (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/OPERATIONS.md",
    "docs/ROADMAP.md",
):
    require(name, "REAL_INVENTORY_MUTATIONS_ENABLED=false")

require(
    "docs/ARCHITECTURE.md",
    "REAL_INVENTORY_MUTATIONS_ENABLED",
)
require(
    "docs/ARCHITECTURE.md",
    "Production default остаётся `false`.",
)

require(
    "README.md",
    "Первоначальное production-наполнение склада также завершено:",
)
require(
    "README.md",
    "Повторный initial bootstrap запрещён.",
)

require(
    "docs/DEPLOYMENT.md",
    "## Initial production inventory bootstrap",
)

require(
    "docs/OPERATIONS.md",
    "## Initial production inventory bootstrap — accepted",
)

require(
    "docs/OPERATIONS.md",
    "INITIAL_PRODUCTION_BOOTSTRAP=PASS",
)
require(
    "docs/OPERATIONS.md",
    "POST_IMPORT_RECONCILIATION=ZERO_DRIFT",
)
require(
    "docs/OPERATIONS.md",
    "POST_IMPORT_BACKUP=PASS",
)

require(
    "docs/ROADMAP.md",
    "Initial bootstrap уже выполнен и повторно не запускается.",
)

require(
    "docs/RECOVERY_RUNBOOK.md",
    "Production now contains real warehouse data",
)

for name in (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/DEVELOPMENT.md",
    "docs/OPERATIONS.md",
    "docs/PRODUCT_REQUIREMENTS.md",
    "docs/RECOVERY_RUNBOOK.md",
    "docs/ROADMAP.md",
):
    for stale_value in (
        "REAL_INVENTORY_ENTRY=BLOCKED_PENDING_NEXT_ROADMAP",
        "CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED",
        "REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP",
        "Stage15C: `ACTIVE`",
        "не должен считаться уже развёрнутым",
    ):
        forbid(name, stale_value)


# ---------------------------------------------------------------------------
# Historical Stage15 evidence remains historical
# ---------------------------------------------------------------------------

require(
    "docs/STAGE15_PLAN.md",
    "Этот документ является historical acceptance record Stage 15.",
)
require(
    "docs/STAGE15_PLAN.md",
    "CURRENT_AUTHORITATIVE_INVENTORY_SOURCE=NOT_DEFINED",
)
require(
    "docs/STAGE15_PLAN.md",
    "REAL_DATA_IMPORT=DEFERRED_NEXT_ROADMAP",
)
require(
    "docs/STAGE15_PLAN.md",
    "STAGE15=TECHNICAL_HARDENING_COMPLETE",
)
require(
    "docs/STAGE15_PLAN.md",
    "INITIAL_PRODUCTION_BOOTSTRAP=PASS",
)

require(
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "Это historical remediation tracker pre-data hardening.",
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
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "INITIAL_PRODUCTION_BOOTSTRAP=PASS",
)


# ---------------------------------------------------------------------------
# Development / architecture / UI contracts
# ---------------------------------------------------------------------------

require(
    "docs/DEVELOPMENT.md",
    "npx playwright install chromium webkit",
)
require(
    "docs/DEVELOPMENT.md",
    "frontend/e2e/warehouse-v2.spec.ts",
)
require(
    "docs/DEVELOPMENT.md",
    "npm run test:e2e:fullstack",
)

for stale_value in (
    "frontend/e2e/stage8.spec.ts",
    "latest serial state",
    "allocation и reactivation/reversal races",
    "Production остаётся на `f1a2b3c4d5e6`",
):
    forbid(
        "docs/DEVELOPMENT.md",
        stale_value,
    )

require(
    "docs/ARCHITECTURE.md",
    "org.opencontainers.image.revision",
)
require(
    "docs/ARCHITECTURE.md",
    "app.bootstrap.production_inventory",
)
forbid(
    "docs/ARCHITECTURE.md",
    "Production migration head до Stage 8B release",
)

require(
    "docs/DEPLOYMENT.md",
    "docs/RECOVERY_RUNBOOK.md",
)
require(
    "docs/DEPLOYMENT.md",
    "python -m app.bootstrap.production_inventory",
)
forbid(
    "docs/DEPLOYMENT.md",
    "Текущий accepted production source:",
)

require(
    "docs/PRODUCT_REQUIREMENTS.md",
    "Warehouse Domain V2 развёрнут и принят в production.",
)
require(
    "docs/PRODUCT_REQUIREMENTS.md",
    "атомарно создаёт target StorageLocation",
)
for stale_value in (
    "Начальный workbook импортируется только в явно существующую StorageLocation.",
    "dry-run не изменяет БД.",
):
    forbid(
        "docs/PRODUCT_REQUIREMENTS.md",
        stale_value,
    )

forbid(
    "docs/DEPLOYMENT.md",
    "`inventory_units`",
)

require(
    "docs/OPERATIONS.md",
    "desktop-capable runtime автоматически запрашивает fullscreen",
)
require(
    "docs/OPERATIONS.md",
    "merged topic branches удаляются после acceptance",
)
require(
    "docs/DEPLOYMENT.md",
    "host-side `ops/`",
)

for stale_value in (
    "остаются обязательными перед снятием",
    "repository visibility — отдельное explicit решение перед снятием",
):
    forbid(
        "docs/OPERATIONS.md",
        stale_value,
    )

require(
    "docs/ROADMAP.md",
    "## 10. Current stabilization / closeout",
)
require(
    "docs/ROADMAP.md",
    "- [x] Canonical documentation reconciled with accepted production state.",
)


# ---------------------------------------------------------------------------
# Recovery contract documentation
# ---------------------------------------------------------------------------

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


print("DOCS_FRESHNESS_CONTRACT=PASS")
