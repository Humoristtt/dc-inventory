#!/usr/bin/env python3
"""Проверка единой current-state карты Markdown без исторических ledgers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs/README.md"

EXPECTED_DOCS = {
    "README.md",
    "AGENTS.md",
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
    "frontend/vendor/telegram-web-app.SOURCE.md",
}

FORBIDDEN_LEGACY_DOCS = {
    "docs/AUDIT_0_12_REMEDIATION.md",
    "docs/CATALOG_SCHEMA.md",
    "docs/CATALOG_SOURCE_REFERENCE.md",
    "docs/CP07_HTTP_SOCKET_MIGRATION.md",
    "docs/CP13_DOCUMENTATION_AUDIT.md",
    "docs/FRONTEND_DESIGN_SYSTEM.md",
    "docs/FRONTEND_PERFORMANCE.md",
    "docs/HISTORY.md",
    "docs/MASTER_REMEDIATION_PLAN.md",
    "docs/RBAC_PROCUREMENT.md",
    "docs/ROADMAP.md",
    "docs/STAGE15_AUDIT_REMEDIATION.md",
    "docs/STAGE15_PLAN.md",
    "docs/WAREHOUSE_DOMAIN.md",
}

assert INDEX.is_file(), "Отсутствует docs/README.md"
index_text = INDEX.read_text(encoding="utf-8")

tracked = {
    path
    for path in subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=ROOT,
    ).decode().split("\0")
    if path
}

assert tracked == EXPECTED_DOCS, (
    "Набор Markdown расходится с current-state картой: "
    f"missing={sorted(EXPECTED_DOCS - tracked)}, "
    f"extra={sorted(tracked - EXPECTED_DOCS)}"
)
assert not tracked.intersection(FORBIDDEN_LEGACY_DOCS)

links = re.findall(r"\]\(([^)#]+\.md)\)", index_text)
resolved = set()

for link in links:
    target = (INDEX.parent / link).resolve()
    assert target.is_relative_to(ROOT), f"Ссылка вне репозитория: {link}"
    assert target.is_file(), f"Битая ссылка: {link}"
    resolved.add(target.relative_to(ROOT).as_posix())

expected_index_targets = EXPECTED_DOCS - {"docs/README.md"}
assert resolved == expected_index_targets, (
    "docs/README.md обязан перечислять каждый Markdown ровно как current resource: "
    f"missing={sorted(expected_index_targets - resolved)}, "
    f"extra={sorted(resolved - expected_index_targets)}"
)

for required in (
    "актуальную документацию текущей реализации",
    "При расхождении приоритет",
    "CURRENT_STATE_AUDIT.md",
    "ARCHITECTURE.md",
    "OPERATIONS.md",
    "RECOVERY_RUNBOOK.md",
):
    assert required in index_text, required

for stale_word in (
    "Исторические и справочные документы",
    "не переписывать историю чекпойнтов",
    "Stage 15",
    "CP-00",
):
    assert stale_word not in index_text, stale_word

print(
    "DOCS_STRUCTURE=PASS "
    f"({len(tracked)} tracked Markdown, current-state only)"
)
