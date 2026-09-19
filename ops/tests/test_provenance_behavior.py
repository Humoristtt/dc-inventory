#!/usr/bin/env python3
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("provenance", ROOT / "ops/backup/runtime_provenance.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProvenanceTests(unittest.TestCase):
    def test_image_labels_override_container_claims_for_all_services(self):
        image_id = "sha256:" + "a" * 64
        revision = "b" * 40
        container = {"State": {"Running": True}, "Image": image_id,
                     "Config": {"Labels": {module.REVISION_LABEL: "c" * 40}}}
        image = {"Config": {"Labels": {module.REVISION_LABEL: revision}}}
        for service in ("backend", "web", "postgres", "telegram-worker", "maintenance-worker"):
            with patch.object(module, "run", return_value="container"), \
                 patch.object(module.subprocess, "run", side_effect=[
                     SimpleNamespace(stdout=json.dumps([container])),
                     SimpleNamespace(stdout=json.dumps([image])),
                 ]) as run:
                result = module.collect(ROOT, None, service)
            self.assertEqual(result, {"image_id": image_id, "source_revision": revision})
            self.assertEqual(run.call_args.args[0], ["docker", "image", "inspect", image_id])

    def test_claimed_checkout_must_match_actual_git_head(self):
        actual = "a" * 40
        claimed = "b" * 40

        with patch.object(
            module.subprocess,
            "check_output",
            return_value=actual + "\n",
        ) as git:
            module.verify_checkout(ROOT, actual)

            with self.assertRaisesRegex(RuntimeError, "mismatch"):
                module.verify_checkout(ROOT, claimed)

            self.assertEqual(git.call_count, 2)
            self.assertEqual(git.call_args.args, (["git", "rev-parse", "HEAD"],))
            self.assertEqual(git.call_args.kwargs["cwd"], ROOT)

        with patch.object(module.subprocess, "check_output") as git:
            with self.assertRaisesRegex(RuntimeError, "invalid production checkout SHA"):
                module.verify_checkout(ROOT, "invalid")
            git.assert_not_called()

    def test_missing_container_fails_closed(self):
        with patch.object(module, "run", return_value=""):
            with self.assertRaises(RuntimeError):
                module.collect(ROOT, None, "postgres")

    def test_email_delivery_flag_is_read_from_backend_container(self):
        inspected = {"Config": {"Env": ["EMAIL_DELIVERY_ENABLED=false"]}}
        with patch.object(module, "run", return_value="backend-container"), patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=json.dumps([inspected])),
        ):
            self.assertFalse(module.email_delivery_enabled(ROOT, None))

    def test_email_delivery_flag_must_be_explicit(self):
        inspected = {"Config": {"Env": []}}
        with patch.object(module, "run", return_value="backend-container"), patch.object(
            module.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=json.dumps([inspected])),
        ):
            with self.assertRaises(RuntimeError):
                module.email_delivery_enabled(ROOT, None)


if __name__ == "__main__":
    unittest.main()
