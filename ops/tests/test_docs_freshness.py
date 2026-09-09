#!/usr/bin/env python3
import ast
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


def source_alembic_heads() -> set[str]:
    versions = ROOT / "backend/migrations/versions"
    revisions: set[str] = set()
    parents: set[str] = set()

    for path in versions.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))

        revision: str | None = None
        down_revisions: list[str] = []

        for node in tree.body:
            name: str | None = None
            value_node: ast.expr | None = None

            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                name = node.target.id
                value_node = node.value

            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                name = node.targets[0].id
                value_node = node.value

            if name not in {"revision", "down_revision"}:
                continue

            if value_node is None:
                continue

            value = ast.literal_eval(value_node)

            if name == "revision":
                if isinstance(value, str):
                    revision = value
                continue

            if isinstance(value, str):
                down_revisions = [value]
            elif isinstance(value, (tuple, list)):
                down_revisions = [
                    item
                    for item in value
                    if isinstance(item, str)
                ]
            elif value is None:
                down_revisions = []

        if revision is not None:
            revisions.add(revision)
            parents.update(down_revisions)

    return revisions - parents


SOURCE_HEADS = source_alembic_heads()

if len(SOURCE_HEADS) != 1:
    raise RuntimeError(
        f"expected one source Alembic head, got {sorted(SOURCE_HEADS)}"
    )

SOURCE_ALEMBIC_HEAD = next(iter(SOURCE_HEADS))


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

# Accepted production head remains an explicit operational fact in
# production-facing documentation. Source head is derived from the migration
# graph independently.
ACCEPTED_PRODUCTION_ALEMBIC_HEAD = "f8a9b0c1d2e3"

for name in (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/DEVELOPMENT.md",
    "docs/OPERATIONS.md",
):
    require(name, ACCEPTED_PRODUCTION_ALEMBIC_HEAD)

for name in (
    "README.md",
    "docs/DEPLOYMENT.md",
    "docs/DEVELOPMENT.md",
    "docs/OPERATIONS.md",
):
    forbid(name, "c5d6e7f8a9b0")

for name in (
    "README.md",
    "docs/DEVELOPMENT.md",
    "docs/ROADMAP.md",
):
    require(name, SOURCE_ALEMBIC_HEAD)

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

for name, assertion in (
    (
        "README.md",
        "UserItemCustodyBalance",
    ),
    (
        "docs/ARCHITECTURE.md",
        "user_item_custody_balances(User, Item, quantity)",
    ),
    (
        "docs/WAREHOUSE_DOMAIN.md",
        "UserItemCustodyBalance = User × Item × positive quantity",
    ),
    (
        "docs/PRODUCT_REQUIREMENTS.md",
        "UserItemCustodyBalance",
    ),
    (
        "docs/DEVELOPMENT.md",
        "custody является backend integrity projection",
    ),
    (
        "docs/ROADMAP.md",
        "UserItemCustodyBalance = User × Item × positive quantity",
    ),
):
    require(name, assertion)

for name, stale_value in (
    (
        "README.md",
        "legacy serial/custody model не является частью целевой схемы",
    ),
    (
        "README.md",
        "не содержит active serial/WWN/custody/current-holder accounting",
    ),
    (
        "docs/WAREHOUSE_DOMAIN.md",
        "Система не хранит и не вычисляет персональный остаток оборудования",
    ),
    (
        "docs/WAREHOUSE_DOMAIN.md",
        "- custody;",
    ),
    (
        "docs/PRODUCT_REQUIREMENTS.md",
        "Персональный баланс оборудования сотрудников не ведётся.",
    ),
    (
        "docs/DEVELOPMENT.md",
        "catalog/Admin/stock/«Моё» UX",
    ),
):
    forbid(name, stale_value)
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

for assertion in (
    "UFW active;",
    "`PermitRootLogin no`;",
    "`PasswordAuthentication no`;",
    "`X11Forwarding no`;",
    "`GatewayPorts no`;",
    "`AllowTcpForwarding yes` сохраняется",
):
    require(
        "docs/OPERATIONS.md",
        assertion,
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
require(
    "docs/ROADMAP.md",
    "- [x] Выполнить independent full source/security/runtime/data audit на clean baseline.",
)
require(
    "docs/ROADMAP.md",
    "- [x] Исправить findings текущего audit до технически чистого baseline.",
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
