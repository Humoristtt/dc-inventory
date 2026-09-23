"""Functional tests of the actual Stage15 restore download handler.

Uses a temporary fake S3 implementation. No network or production access.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESTORE = ROOT / "ops/recovery/rehearse_restore.sh"
VALIDATOR = ROOT / "ops/recovery/validate_manifest.py"

MANIFEST_KEY = "backups/postgres/full/test.manifest.json"
DUMP_KEY = "backups/postgres/full/test.dump"
CHECKOUT = "c" * 40

MARKER = '  "$STATE" <<\'PY\'\n'
ENDING = "\nPY\n# New manifests"

source = RESTORE.read_text(encoding="utf-8")

if source.count(MARKER) != 1:
    raise RuntimeError("Restore Python entrypoint changed")

handler = source.split(MARKER, 1)[1]

if handler.count(ENDING) != 1:
    raise RuntimeError("Restore Python closing marker changed")

handler = handler.split(ENDING, 1)[0]

compile(handler, str(RESTORE), "exec")


FAKE_HELPER = r'''
import base64
import hashlib
import json
import os

from datetime import datetime, timedelta, timezone
from pathlib import Path


fixture = json.loads(
    Path(os.environ["FAKE_S3_FIXTURE"]).read_text()
)
calls = Path(os.environ["FAKE_S3_CALLS"])


def record(action, key, version):
    with calls.open("a", encoding="utf-8") as output:
        output.write(
            json.dumps([action, key, version]) + "\n"
        )


def load_env(path):
    return {
        "S3_BUCKET": "test-bucket",
        "S3_PREFIX": "backups",
    }


def make_client(env):
    return FakeClient()


def validate_storage(client, env):
    return None


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class FakeClient:
    def object(self, key, version):
        return fixture["objects"][key][version]

    def head_object(self, *, Bucket, Key, VersionId=None):
        assert Bucket == "test-bucket"
        record("head", Key, VersionId)

        if VersionId is None:
            version = fixture["current"][Key]
        else:
            version = VersionId

        data = base64.b64decode(
            self.object(Key, version)["data"]
        )

        returned_version = version

        if fixture.get("wrong_head_key") == Key:
            if VersionId is not None:
                returned_version = "wrong-version"

        return {
            "VersionId": returned_version,
            "ContentLength": len(data),
            "Metadata": {
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        }

    def download_file(
        self, bucket, key, filename, ExtraArgs=None
    ):
        assert bucket == "test-bucket"

        version = (
            ExtraArgs.get("VersionId")
            if ExtraArgs is not None
            else None
        )

        record("download", key, version)

        if version is None:
            version = fixture["current"][key]

        data = base64.b64decode(
            self.object(key, version)["data"]
        )

        if fixture.get("corrupt_download_key") == key:
            data = b"X" * len(data)

        Path(filename).write_bytes(data)

    def get_object_retention(
        self, *, Bucket, Key, VersionId
    ):
        assert Bucket == "test-bucket"
        record("retention", Key, VersionId)

        mode = "GOVERNANCE"

        if fixture.get("bad_retention_key") == Key:
            mode = "COMPLIANCE"

        return {
            "Retention": {
                "Mode": mode,
                "RetainUntilDate": (
                    datetime.now(timezone.utc)
                    + timedelta(days=8)
                ),
            },
        }
'''


def encoded(data: bytes) -> dict[str, str]:
    return {
        "data": base64.b64encode(data).decode("ascii"),
    }


def make_manifest(dump: bytes) -> dict:
    backend = {
        "image_id": "sha256:" + "a" * 64,
        "source_revision": "b" * 40,
    }

    return {
        "schema_version": 2,
        "application": "dc-inventory",
        "backup_type": "full",
        "production_checkout_sha": CHECKOUT,
        "alembic_head": "d4e5f6a7b8c9",
        "postgresql_tools": "pg_dump (PostgreSQL) 18.0",
        "artifact": {
            "key": DUMP_KEY,
            "sha256": hashlib.sha256(dump).hexdigest(),
            "size_bytes": len(dump),
            "format": "pg_dump-custom",
            "version_id": "dump-v1",
        },
        "runtime": {
            "backend": backend,
            "telegram_worker": backend.copy(),
            "maintenance_worker": backend.copy(),
            "email_worker": {"state": "disabled"},
            "web": {
                "image_id": "sha256:" + "e" * 64,
                "source_revision": "f" * 40,
            },
            "postgres": {
                "image_id": "sha256:" + "1" * 64,
                "source_revision": "2" * 40,
            },
        },
    }


class RestoreVersionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.directory = Path(temporary.name)

        backup_dir = self.directory / "ops/backup"
        recovery_dir = self.directory / "ops/recovery"
        backup_dir.mkdir(parents=True)
        recovery_dir.mkdir(parents=True)

        self.helper = backup_dir / "s3_stage15.py"
        self.helper.write_text(FAKE_HELPER, encoding="utf-8")

        (recovery_dir / "validate_manifest.py").write_text(
            VALIDATOR.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        self.dump = b"synthetic-pg-dump-for-restore-testing"
        self.manifest = make_manifest(self.dump)

        self.state = {
            "schema_version": 2,
            "state": "success",
            "manifest_key": MANIFEST_KEY,
            "dump_key": DUMP_KEY,
            "dump_sha256": hashlib.sha256(
                self.dump
            ).hexdigest(),
            "dump_size_bytes": len(self.dump),
            "runtime": self.manifest["runtime"],
            "manifest_version_id": "manifest-v1",
            "dump_version_id": "dump-v1",
        }

        self.fixture = {
            "current": {
                MANIFEST_KEY: "manifest-v1",
                DUMP_KEY: "dump-v1",
            },
            "objects": {
                MANIFEST_KEY: {},
                DUMP_KEY: {
                    "dump-v1": encoded(self.dump),
                    "dump-new": encoded(b"unrelated dump"),
                },
            },
        }

        self.state_path = self.directory / "state.json"
        self.fixture_path = self.directory / "fixture.json"
        self.calls_path = self.directory / "calls.jsonl"
        self.work_dir = self.directory / "restore"
        self.work_dir.mkdir()

    def execute(self):
        manifest_bytes = (
            json.dumps(
                self.manifest,
                sort_keys=True,
            ) + "\n"
        ).encode("utf-8")

        self.fixture["objects"][MANIFEST_KEY] = {
            "manifest-v1": encoded(manifest_bytes),
            "manifest-new": encoded(b"{}"),
        }

        self.state_path.write_text(
            json.dumps(self.state),
            encoding="utf-8",
        )
        self.fixture_path.write_text(
            json.dumps(self.fixture),
            encoding="utf-8",
        )

        environment = dict(os.environ)
        environment["FAKE_S3_FIXTURE"] = str(
            self.fixture_path
        )
        environment["FAKE_S3_CALLS"] = str(
            self.calls_path
        )

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                handler,
                str(self.helper),
                str(self.directory / "unused.env"),
                MANIFEST_KEY,
                str(self.work_dir),
                CHECKOUT,
                str(self.state_path),
            ],
            cwd=self.directory,
            env=environment,
            text=True,
            capture_output=True,
        )

        calls = []

        if self.calls_path.exists():
            calls = [
                json.loads(line)
                for line in self.calls_path.read_text().splitlines()
            ]

        return result, calls

    def assert_success(self, result):
        self.assertEqual(
            result.returncode,
            0,
            result.stdout + result.stderr,
        )
        self.assertIn(
            "RESTORE_DOWNLOAD_VERIFICATION=PASS",
            result.stdout,
        )

    def assert_failure(self, result):
        self.assertNotEqual(
            result.returncode,
            0,
            "Restore unexpectedly accepted invalid data",
        )
        self.assertNotIn(
            "RESTORE_DOWNLOAD_VERIFICATION=PASS",
            result.stdout,
        )

    def test_exact_versions(self):
        result, calls = self.execute()
        self.assert_success(result)

        downloads = [
            call for call in calls
            if call[0] == "download"
        ]

        self.assertEqual(downloads, [
            ["download", MANIFEST_KEY, "manifest-v1"],
            ["download", DUMP_KEY, "dump-v1"],
        ])

    def test_changed_current_versions_do_not_affect_restore(self):
        self.fixture["current"][MANIFEST_KEY] = "manifest-new"
        self.fixture["current"][DUMP_KEY] = "dump-new"

        result, calls = self.execute()
        self.assert_success(result)

        self.assertNotIn(
            ["download", MANIFEST_KEY, "manifest-new"],
            calls,
        )
        self.assertNotIn(
            ["download", DUMP_KEY, "dump-new"],
            calls,
        )

    def test_mismatched_state_dump_version_fails_closed(self):
        self.state["dump_version_id"] = "dump-new"

        result, calls = self.execute()
        self.assert_failure(result)

        self.assertFalse(
            any(
                call[0] == "download"
                and call[1] == DUMP_KEY
                for call in calls
            )
        )

    def test_incomplete_state_versions_fail_closed(self):
        del self.state["dump_version_id"]

        result, _ = self.execute()
        self.assert_failure(result)

    def test_corrupt_dump_fails_closed(self):
        self.fixture["corrupt_download_key"] = DUMP_KEY

        result, _ = self.execute()
        self.assert_failure(result)

    def test_wrong_head_version_fails_closed(self):
        self.fixture["wrong_head_key"] = MANIFEST_KEY

        result, _ = self.execute()
        self.assert_failure(result)

    def test_wrong_retention_fails_closed(self):
        self.fixture["bad_retention_key"] = DUMP_KEY

        result, _ = self.execute()
        self.assert_failure(result)

    def test_legacy_backup_pins_current_versions(self):
        del self.state["manifest_version_id"]
        del self.state["dump_version_id"]
        del self.manifest["artifact"]["version_id"]

        result, calls = self.execute()
        self.assert_success(result)

        self.assertIn(
            ["head", MANIFEST_KEY, None],
            calls,
        )
        self.assertIn(
            ["head", DUMP_KEY, None],
            calls,
        )

        downloads = [
            call for call in calls
            if call[0] == "download"
        ]

        self.assertEqual(downloads, [
            ["download", MANIFEST_KEY, "manifest-v1"],
            ["download", DUMP_KEY, "dump-v1"],
        ])

    def test_legacy_backup_does_not_guess_old_versions(self):
        del self.state["manifest_version_id"]
        del self.state["dump_version_id"]
        del self.manifest["artifact"]["version_id"]

        self.fixture["current"][MANIFEST_KEY] = "manifest-new"

        result, _ = self.execute()
        self.assert_failure(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
