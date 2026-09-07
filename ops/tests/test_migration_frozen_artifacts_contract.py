#!/usr/bin/env python3

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "backend" / "migrations" / "versions"

tracked = set(
    subprocess.check_output(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
    ).splitlines()
)

pattern = re.compile(
    r"_frozen\(['\"](?P<name>[^'\"]+)['\"]\)"
)

checked = 0

for migration in MIGRATIONS.glob("*.py"):
    text = migration.read_text()

    if "migrations" not in str(migration):
        continue

    revision_match = re.search(
        r"^revision:\s*str\s*=\s*['\"](?P<revision>[^'\"]+)['\"]",
        text,
        re.MULTILINE,
    )

    if revision_match is None:
        continue

    revision = revision_match.group("revision")

    for match in pattern.finditer(text):
        name = match.group("name")
        relative = (
            Path("backend")
            / "migrations"
            / "data"
            / f"{revision}_{name}.json"
        )
        path = ROOT / relative

        if not path.is_file():
            raise RuntimeError(
                f"{migration.name}: missing frozen migration artifact {relative}"
            )

        if relative.as_posix() not in tracked:
            raise RuntimeError(
                f"{migration.name}: frozen migration artifact is not tracked by git: "
                f"{relative}"
            )

        checked += 1

if checked == 0:
    raise RuntimeError("no frozen migration artifacts were checked")

print(f"MIGRATION_FROZEN_ARTIFACTS_CONTRACT=PASS checked={checked}")
