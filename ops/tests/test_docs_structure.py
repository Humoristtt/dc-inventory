#!/usr/bin/env python3
"""Проверка карты Markdown, ссылок и границ текущих/исторических документов."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INDEX = ROOT / "docs/README.md"
assert INDEX.is_file(), "Отсутствует карта docs/README.md"
text = INDEX.read_text(encoding="utf-8")

links = re.findall(r"\]\(([^)#]+\.md)\)", text)
assert links, "В карте документации нет ссылок на Markdown"

resolved = set()
for link in links:
    target = (INDEX.parent / link).resolve()
    assert target.is_relative_to(ROOT), f"Ссылка вне репозитория: {link}"
    assert target.is_file(), f"Битая ссылка: {link}"
    resolved.add(target.relative_to(ROOT).as_posix())

tracked = {
    path
    for path in subprocess.check_output(
        ["git", "ls-files", "-z", "--", "*.md"], cwd=ROOT
    ).decode().split("\0")
    if path
}
assert "docs/README.md" in tracked
missing = tracked - {"docs/README.md"} - resolved
extra = resolved - tracked
assert not missing, f"Markdown без категории в docs/README.md: {sorted(missing)}"
assert not extra, f"Оглавление ссылается на незакоммиченные Markdown: {sorted(extra)}"

for needle in (
    "Нормативные документы",
    "Исторические",
    "production",
    "a9c0d1e2f3a4",
    "c3d4e5f6a7b8",
    "CP-07",
    "CP-00–18",
):
    assert needle.lower() in text.lower(), f"Нет нужной границы: {needle}"

print(f"DOCS_STRUCTURE=PASS ({len(tracked)} tracked Markdown, {len(resolved)} unique targets)")
