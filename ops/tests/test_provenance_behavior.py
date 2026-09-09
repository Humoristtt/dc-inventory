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

    def test_missing_container_fails_closed(self):
        with patch.object(module, "run", return_value=""):
            with self.assertRaises(RuntimeError):
                module.collect(ROOT, None, "postgres")


if __name__ == "__main__":
    unittest.main()
