#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/backup/check_status.py"
spec = importlib.util.spec_from_file_location("backup_status", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupStatusTests(unittest.TestCase):
    def test_readiness_cases(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            root = Path(directory)
            self.assertFalse(module.check(root, 100, now)["ready"])
            success = {"schema_version": 2, "state": "success",
                       "started_at_utc": (now - timedelta(seconds=100)).isoformat(),
                       "verified_at_utc": now.isoformat()}
            (root / "last-success.json").write_text(json.dumps(success))
            (root / "status.json").write_text(json.dumps(success))
            self.assertTrue(module.check(root, 100, now)["ready"])
            self.assertEqual(module.check(root, 99, now)["reason"], "stale_backup")
            (root / "status.json").write_text('{"state":"failure"}')
            self.assertEqual(module.check(root, 100, now)["reason"], "last_attempt_failed")
            (root / "status.json").write_text(json.dumps(success))
            self.assertFalse(module.check(root, 100, now - timedelta(seconds=1))["ready"])
            for invalid in ("[]", "null", "{", '{"state":"success"}'):
                (root / "last-success.json").write_text(invalid)
                self.assertFalse(module.check(root, 100, now)["ready"])

    def test_cli_nonzero_and_units(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "tmp") as directory:
            result = subprocess.run([sys.executable, str(SCRIPT), "--state-dir", directory],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["ready"])
        for name in ("s3", "status"):
            source = (ROOT / f"ops/systemd/dc-inventory-backup-{name}.service").read_text()
            self.assertIn("OnFailure=dc-inventory-backup-alert.service", source)
        self.assertIn("OnUnitActiveSec=15min", (
            ROOT / "ops/systemd/dc-inventory-backup-status.timer").read_text())


if __name__ == "__main__":
    (ROOT / "tmp").mkdir(exist_ok=True)
    unittest.main()
