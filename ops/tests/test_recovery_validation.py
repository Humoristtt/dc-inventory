#!/usr/bin/env python3
import copy
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_KEY = "backups/postgres/full/2026/09/19/dc-inventory-test.manifest.json"
PREFIX = "backups/"
spec = importlib.util.spec_from_file_location(
    "restore_manifest", ROOT / "ops/recovery/validate_manifest.py"
)
manifest_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest_module)


def valid_manifest():
    backend = {"image_id": "sha256:" + "a" * 64, "source_revision": "b" * 40}
    return {
        "schema_version": 2,
        "application": "dc-inventory",
        "backup_type": "full",
        "production_checkout_sha": "c" * 40,
        "alembic_head": "d4e5f6a7b8c9",
        "postgresql_tools": "pg_dump (PostgreSQL) 18.0",
        "artifact": {
            "key": MANIFEST_KEY.removesuffix(".manifest.json") + ".dump",
            "sha256": "d" * 64,
            "size_bytes": 100,
            "format": "pg_dump-custom",
        },
        "runtime": {
            "backend": backend,
            "telegram_worker": backend.copy(),
            "maintenance_worker": backend.copy(),
            "email_worker": {"state": "disabled"},
            "web": {"image_id": "sha256:" + "e" * 64, "source_revision": "f" * 40},
            "postgres": {"image_id": "sha256:" + "1" * 64, "source_revision": "2" * 40},
        },
    }


class RecoveryValidationTests(unittest.TestCase):
    def test_valid_and_legacy_runtime_manifests(self):
        manifest = valid_manifest()
        self.assertIs(manifest_module.validate_manifest(manifest, MANIFEST_KEY, PREFIX), manifest)
        del manifest["runtime"]["email_worker"]
        del manifest["runtime"]["postgres"]
        self.assertIs(manifest_module.validate_manifest(manifest, MANIFEST_KEY, PREFIX), manifest)

    def test_mismatched_or_corrupt_manifest_fails_closed(self):
        changes = [
            lambda m: m.update(application="other"),
            lambda m: m.update(production_checkout_sha="not-a-sha"),
            lambda m: m["artifact"].update(key="backups/other.dump"),
            lambda m: m["artifact"].update(sha256="invalid"),
            lambda m: m["artifact"].update(size_bytes=0),
            lambda m: m["artifact"].update(size_bytes=True),
            lambda m: m["artifact"].update(format="plain"),
            lambda m: m["runtime"]["telegram_worker"].update(image_id="sha256:" + "0" * 64),
            lambda m: m["runtime"]["web"].update(source_revision="invalid"),
            lambda m: m["runtime"]["email_worker"].update(image_id="sha256:" + "0" * 64),
        ]
        for change in changes:
            manifest = copy.deepcopy(valid_manifest())
            change(manifest)
            with self.subTest(change=change), self.assertRaises(ValueError):
                manifest_module.validate_manifest(manifest, MANIFEST_KEY, PREFIX)
        with self.assertRaises(ValueError):
            manifest_module.validate_manifest(valid_manifest(), "backups/other.manifest.json", PREFIX)

    def test_cleanup_removes_only_resources_created_by_this_run(self):
        script = (ROOT / "ops/recovery/rehearse_restore.sh").read_text()
        cleanup = script.split("cleanup_runtime() (", 1)[1].split("\n)\ntrap cleanup_runtime EXIT", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            calls = Path(temporary) / "calls"
            bash = f'''set -e
RESTORE_APP=dc-inventory-restore-app-test
RESTORE_PG=dc-inventory-restore-pg-test
RESTORE_VOL=dc-inventory-restore-vol-test
RESTORE_NET=dc-inventory-restore-net-test
WORK_DIR=/tmp/never-delete
RESTORE_APP_CREATED=false
RESTORE_PG_CREATED=false
RESTORE_VOL_CREATED=false
RESTORE_NET_CREATED=false
CALLS={calls}
docker() {{ printf '%s\n' "$*" >> "$CALLS"; }}
cleanup_runtime() ({cleanup}
)
cleanup_runtime
test ! -e "$CALLS"
RESTORE_APP_CREATED=true
RESTORE_PG_CREATED=true
RESTORE_VOL_CREATED=true
RESTORE_NET_CREATED=true
cleanup_runtime
'''
            subprocess.run(["bash", "-c", bash], check=True)
            self.assertEqual(calls.read_text().splitlines(), [
                "rm -f dc-inventory-restore-app-test",
                "rm -f dc-inventory-restore-pg-test",
                "volume rm dc-inventory-restore-vol-test",
                "network rm dc-inventory-restore-net-test",
            ])

    def test_invalid_env_line_does_not_echo_secret(self):
        boto3 = types.ModuleType("boto3")
        botocore = types.ModuleType("botocore")
        config = types.ModuleType("botocore.config")
        config.Config = object
        botocore.config = config
        lifecycle = types.ModuleType("lifecycle_policy")
        lifecycle.require_rule_applies_to_prefix = lambda *a, **k: None
        with patch.dict(sys.modules, {"boto3": boto3, "botocore": botocore,
                                      "botocore.config": config, "lifecycle_policy": lifecycle}):
            s3_spec = importlib.util.spec_from_file_location(
                "stage15_s3_test", ROOT / "ops/backup/s3_stage15.py"
            )
            s3_module = importlib.util.module_from_spec(s3_spec)
            s3_spec.loader.exec_module(s3_module)
        with tempfile.TemporaryDirectory() as temporary:
            env_file = Path(temporary) / "bad.env"
            env_file.write_text("secret-without-equals\n")
            with self.assertRaisesRegex(RuntimeError, "Invalid env line 1") as raised:
                s3_module.load_env(env_file)
            self.assertNotIn("secret-without-equals", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
