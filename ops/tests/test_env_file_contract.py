#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "ops/validate_env_file.py"
EXAMPLE = ROOT / ".env.example"


def run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(VALIDATOR),
            str(path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


valid = run(EXAMPLE)
assert valid.returncode == 0, valid.stderr
assert "ENV_FILE_KEYS=PASS" in valid.stdout

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    typo = root / "typo.env"
    typo.write_text(
        "DATABASE_URL=postgresql://example\n"
        "DATABASE_POOL_SZE=10\n"
    )

    result = run(typo)
    assert result.returncode == 1
    assert (
        "unknown environment key DATABASE_POOL_SZE"
        in result.stderr
    )

    duplicate = root / "duplicate.env"
    duplicate.write_text(
        "APP_ENV=test\n"
        "APP_ENV=production\n"
    )

    result = run(duplicate)
    assert result.returncode == 1
    assert "duplicate key APP_ENV" in result.stderr

    malformed = root / "malformed.env"
    malformed.write_text(
        "APP_ENV=test\n"
        "THIS IS NOT AN ASSIGNMENT\n"
    )

    result = run(malformed)
    assert result.returncode == 1
    assert "invalid env assignment" in result.stderr

print("ENV_FILE_CONTRACT=PASS")
