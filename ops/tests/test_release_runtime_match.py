#!/usr/bin/env python3
"""Offline verification of approved release/runtime image identity."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/release/verify_release_runtime.py"

spec = importlib.util.spec_from_file_location("release_runtime", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = "a" * 40
DIFFERENT_SHA = "b" * 40


def fixtures():
    ids = {
        "backend": "sha256:" + "1" * 64,
        "web": "sha256:" + "2" * 64,
        "postgres": "sha256:" + "3" * 64,
    }

    release = {
        "schema_version": 1,
        "source_revision": SHA,
        "images": {
            name: {
                "image_id": image_id,
                "source_revision": SHA,
                "reference": f"dc-inventory-{name}:{SHA}",
                "repo_digests": [],
            }
            for name, image_id in ids.items()
        },
    }

    runtime = {
        "schema_version": 1,
        "production_checkout_sha": SHA,
        "runtime": {
            name: {
                "image_id": image_id,
                "source_revision": SHA,
            }
            for name, image_id in ids.items()
        },
    }

    runtime["runtime"]["telegram_worker"] = copy.deepcopy(
        runtime["runtime"]["backend"]
    )
    runtime["runtime"]["maintenance_worker"] = copy.deepcopy(
        runtime["runtime"]["backend"]
    )
    runtime["runtime"]["email_worker"] = {"state": "disabled"}

    return release, runtime


class ReleaseRuntimeTests(unittest.TestCase):
    def test_exact_release_matches(self):
        release, runtime = fixtures()
        module.verify(release, runtime)

    def test_checkout_mismatch_fails_closed(self):
        release, runtime = fixtures()
        runtime["production_checkout_sha"] = DIFFERENT_SHA

        with self.assertRaisesRegex(
            ValueError,
            "production checkout SHA mismatch",
        ):
            module.verify(release, runtime)

    def test_all_three_services_reject_different_image_ids(self):
        for service in module.SERVICES:
            with self.subTest(service=service):
                release, runtime = fixtures()
                runtime["runtime"][service]["image_id"] = (
                    "sha256:" + "4" * 64
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "runtime image ID mismatch",
                ):
                    module.verify(release, runtime)

    def test_revision_mismatch_rejected(self):
        release, runtime = fixtures()
        runtime["runtime"]["web"]["source_revision"] = DIFFERENT_SHA

        with self.assertRaisesRegex(ValueError, "runtime revision mismatch"):
            module.verify(release, runtime)

    def test_worker_image_mismatch_rejected(self):
        release, runtime = fixtures()
        runtime["runtime"]["telegram_worker"]["image_id"] = (
            "sha256:" + "4" * 64
        )

        with self.assertRaisesRegex(ValueError, "backend image mismatch"):
            module.verify(release, runtime)

    def test_enabled_email_must_match_backend(self):
        release, runtime = fixtures()
        runtime["runtime"]["email_worker"] = {
            "state": "enabled",
            **runtime["runtime"]["backend"],
        }
        module.verify(release, runtime)

        runtime["runtime"]["email_worker"]["image_id"] = (
            "sha256:" + "4" * 64
        )

        with self.assertRaisesRegex(ValueError, "backend image mismatch"):
            module.verify(release, runtime)

    def test_missing_or_invalid_fields_rejected(self):
        cases = (
            lambda release, runtime: release.update(schema_version=2),
            lambda release, runtime: release["images"].pop("web"),
            lambda release, runtime: runtime["runtime"]["postgres"].update(
                image_id="not-an-image-id"
            ),
            lambda release, runtime: runtime["runtime"].pop("backend"),
            lambda release, runtime: runtime["runtime"].update(
                email_worker={"state": "unknown"}
            ),
        )

        for change in cases:
            with self.subTest(change=change):
                release, runtime = fixtures()
                change(release, runtime)

                with self.assertRaises((ValueError, KeyError, TypeError)):
                    module.verify(release, runtime)

    def test_ci_and_deployment_gate_are_declared(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        deployment = (ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")

        self.assertIn(
            "python3 ops/tests/test_release_runtime_match.py", ci
        )
        self.assertIn(
            "python3 ops/release/verify_release_runtime.py", deployment
        )
        self.assertIn("--release-manifest", deployment)
        self.assertIn("--runtime-provenance", deployment)
        self.assertIn("RELEASE_RUNTIME_MATCH=PASS", deployment)

    def test_cli_pass_and_fail(self):
        release, runtime = fixtures()

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            release_file = directory / "release.json"
            runtime_file = directory / "runtime.json"

            release_file.write_text(json.dumps(release))
            runtime_file.write_text(json.dumps(runtime))

            command = [
                sys.executable,
                str(SCRIPT),
                "--release-manifest",
                str(release_file),
                "--runtime-provenance",
                str(runtime_file),
            ]

            passed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertIn("RELEASE_RUNTIME_MATCH=PASS", passed.stdout)

            runtime["runtime"]["web"]["image_id"] = "sha256:" + "4" * 64
            runtime_file.write_text(json.dumps(runtime))

            failed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("RELEASE_RUNTIME_MATCH=FAIL", failed.stderr)


if __name__ == "__main__":
    unittest.main()
