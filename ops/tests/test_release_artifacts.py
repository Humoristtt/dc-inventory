#!/usr/bin/env python3
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release", ROOT / "ops/release/build_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseTests(unittest.TestCase):
    def test_refs_and_invalid_revision(self):
        sha = "a" * 40
        refs = module.release_refs(sha)
        self.assertEqual(refs["POSTGRES_IMAGE"], f"dc-inventory-postgres:{sha}")
        for value in ("main", "unknown", "a" * 7, "A" * 40):
            with self.assertRaises(ValueError):
                module.release_refs(value)

    def test_dirty_or_existing_release_never_builds(self):
        sha = "a" * 40
        for replies in ([" M file"], ["", sha, "29", f"dc-inventory-backend:{sha}"]):
            with patch.object(module, "output", side_effect=replies), \
                    patch.object(module.subprocess, "run") as build:
                with self.assertRaises(RuntimeError):
                    module.build(Path("unused.env"), ROOT / "tmp/should-not-exist")
                build.assert_not_called()

    def test_compose_reference_overrides(self):
        env = dict(__import__("os").environ)
        env.update(module.release_refs("a" * 40))
        # No dotenv is read and no containers are started.
        command = ["docker", "compose", "--env-file", "/dev/null", "-f", str(ROOT / "compose.yaml"),
                   "config", "--images"]
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(set(result.stdout.splitlines()), set(module.release_refs("a" * 40).values()))
        for variable in ("BACKEND_IMAGE", "WEB_IMAGE", "POSTGRES_IMAGE"):
            env[variable] = f"registry.invalid/{variable.lower()}@sha256:" + "b" * 64
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True)
        self.assertEqual(set(result.stdout.splitlines()), {env[v] for v in module.SERVICES.values()})


if __name__ == "__main__":
    unittest.main()
