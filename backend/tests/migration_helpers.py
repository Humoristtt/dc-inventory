"""Migration commands scoped to a database created by the test fixture."""

import os
import subprocess
import sys
from pathlib import Path


def alembic(url, *arguments, success=True):
    result = subprocess.run(
        [str(Path(sys.executable).with_name("alembic")), *arguments],
        cwd=Path(__file__).parents[1],
        env={**os.environ, "DATABASE_URL": url, "APP_ENV": "test"},
        capture_output=True,
        text=True,
    )
    if success:
        assert result.returncode == 0, result.stderr
    else:
        assert result.returncode != 0
    return result.stdout + result.stderr
