#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release", ROOT / "ops/release/build_release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseTests(unittest.TestCase):
    def release_outputs(self, *, bad_label=False, bad_id=False):
        sha = "a" * 40
        replies = ["", sha, "29", ""]
        for service in module.SERVICES:
            replies.append(json.dumps({
                "Config": {"Labels": {"org.opencontainers.image.revision":
                                      "b" * 40 if bad_label and service == "web" else sha}},
                "Id": "invalid" if bad_id and service == "web" else "sha256:" + "c" * 64,
                "RepoDigests": [],
            }))
        return replies

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

    def test_build_writes_verified_artifacts(self):
        sha = "a" * 40
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release"
            with patch.object(module, "output", side_effect=self.release_outputs()), \
                    patch.object(module.subprocess, "run") as compose:
                module.build(Path("unused.env"), destination)
            compose.assert_called_once()
            manifest = json.loads((destination / "release.json").read_text())
            self.assertEqual(manifest["source_revision"], sha)
            self.assertEqual(set(manifest["images"]), set(module.SERVICES))
            self.assertTrue(all(image["image_id"] == "sha256:" + "c" * 64
                                for image in manifest["images"].values()))
            self.assertIn(f"APP_REVISION={sha}\n", (destination / "release.env").read_text())

    def test_failed_build_or_inspection_leaves_no_release_output(self):
        cases = [
            (self.release_outputs(), subprocess.CalledProcessError(1, "docker compose build")),
            (self.release_outputs(bad_label=True), None),
            (self.release_outputs(bad_id=True), None),
        ]
        for replies, build_error in cases:
            with self.subTest(build_error=build_error, replies=replies[-2:]), \
                    tempfile.TemporaryDirectory() as temporary:
                destination = Path(temporary) / "release"
                with patch.object(module, "output", side_effect=replies), \
                        patch.object(module.subprocess, "run", side_effect=build_error):
                    with self.assertRaises((RuntimeError, subprocess.CalledProcessError)):
                        module.build(Path("unused.env"), destination)
                self.assertFalse(destination.exists())
                self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_failed_artifact_write_leaves_no_release_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release"
            with patch.object(module, "output", side_effect=self.release_outputs()), \
                    patch.object(module.subprocess, "run"), \
                    patch.object(Path, "write_text", side_effect=OSError("write failed")):
                with self.assertRaisesRegex(OSError, "write failed"):
                    module.build(Path("unused.env"), destination)
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_existing_output_is_not_overwritten_or_rebuilt(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "release"
            destination.mkdir()
            marker = destination / "keep.txt"
            marker.write_text("keep")
            with patch.object(module, "output") as command, \
                    patch.object(module.subprocess, "run") as compose:
                with self.assertRaises(FileExistsError):
                    module.build(Path("unused.env"), destination)
            command.assert_not_called()
            compose.assert_not_called()
            self.assertEqual(marker.read_text(), "keep")

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
