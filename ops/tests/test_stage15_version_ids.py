"""Functional tests for version-pinned Stage15 S3 uploads.

No network, credentials or production resources are used.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "ops/backup/s3_stage15.py"

# The functions under test do not construct a boto3 client.
# Stub the SDK imports so this test also runs on a bare Mac Python.
sys.modules["boto3"] = types.ModuleType("boto3")

botocore = types.ModuleType("botocore")
botocore.__path__ = []
config = types.ModuleType("botocore.config")
config.Config = type("Config", (), {})

sys.modules["botocore"] = botocore
sys.modules["botocore.config"] = config

sys.path.insert(0, str(HELPER.parent))

spec = importlib.util.spec_from_file_location(
    "versioned_stage15_s3", HELPER
)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.tamper_key = None
        self.missing_version_key = None
        self.wrong_response_version_key = None
        self.replace_after_upload_key = None

    def upload_file(self, filename, bucket, key, ExtraArgs):
        assert bucket == "test-bucket"
        assert key not in self.objects

        data = Path(filename).read_bytes()
        version = f"version-{len(self.objects) + 1}"

        self.objects[key] = {
            "data": data,
            "version": version,
            "sha256": ExtraArgs["Metadata"]["sha256"],
            "upload_nonce": ExtraArgs["Metadata"]["upload_nonce"],
        }
        self.calls.append(("upload", key, None))

        if key == self.replace_after_upload_key:
            self.objects[key]["version"] = "foreign-version"
            self.objects[key]["upload_nonce"] = "foreign-upload"

    def head_object(self, *, Bucket, Key, VersionId=None):
        assert Bucket == "test-bucket"
        obj = self.objects[Key]
        self.calls.append(("head", Key, VersionId))

        if VersionId is not None:
            assert VersionId == obj["version"]

        returned_version = obj["version"]

        if (
            Key == self.missing_version_key
            and VersionId is None
        ):
            returned_version = None

        return {
            "VersionId": returned_version,
            "ContentLength": len(obj["data"]),
            "Metadata": {
                "sha256": obj["sha256"],
                "upload_nonce": obj["upload_nonce"],
            },
        }

    def get_object(self, *, Bucket, Key, VersionId):
        assert Bucket == "test-bucket"
        obj = self.objects[Key]
        assert VersionId == obj["version"]

        self.calls.append(("get", Key, VersionId))

        data = obj["data"]
        if Key == self.tamper_key:
            data = b"X" * len(data)

        returned_version = obj["version"]
        if Key == self.wrong_response_version_key:
            returned_version = "unexpected-version"

        return {
            "VersionId": returned_version,
            "Body": io.BytesIO(data),
        }

    def get_object_retention(
        self, *, Bucket, Key, VersionId
    ):
        assert Bucket == "test-bucket"
        assert VersionId == self.objects[Key]["version"]

        self.calls.append(("retention", Key, VersionId))

        return {
            "Retention": {
                "Mode": "GOVERNANCE",
                "RetainUntilDate": (
                    datetime.now(timezone.utc)
                    + timedelta(days=8)
                ),
            },
        }


class VersionedUploadTests(unittest.TestCase):
    DUMP_KEY = "postgres/full/test.dump"
    MANIFEST_KEY = "postgres/full/test.manifest.json"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)

        self.directory = Path(temporary.name)
        self.dump = self.directory / "test.dump"
        self.manifest = self.directory / "test.manifest.json"
        self.versions = self.directory / "versions.json"

        self.dump.write_bytes(b"synthetic-backup-data")
        self.digest = hashlib.sha256(
            self.dump.read_bytes()
        ).hexdigest()

        self.manifest.write_text(
            json.dumps({
                "schema_version": 2,
                "artifact": {
                    "key": self.DUMP_KEY,
                    "sha256": self.digest,
                    "size_bytes": self.dump.stat().st_size,
                    "format": "pg_dump-custom",
                },
            }),
            encoding="utf-8",
        )

        self.client = FakeS3()

        self.args = argparse.Namespace(
            env=self.directory / "unused.env",
            dump=self.dump,
            manifest=self.manifest,
            dump_key=self.DUMP_KEY,
            manifest_key=self.MANIFEST_KEY,
            dump_sha256=self.digest,
            versions_output=self.versions,
        )

    def upload(self):
        with (
            patch.object(
                module,
                "load_env",
                return_value={
                    "S3_BUCKET": "test-bucket",
                    "S3_PREFIX": "postgres",
                },
            ),
            patch.object(
                module,
                "make_client",
                return_value=self.client,
            ),
            patch.object(module, "validate_storage"),
        ):
            module.command_upload(self.args)

    def test_success_records_exact_versions(self):
        self.upload()

        versions = json.loads(
            self.versions.read_text(encoding="utf-8")
        )
        manifest = json.loads(
            self.manifest.read_text(encoding="utf-8")
        )

        self.assertEqual(
            versions["dump_version_id"], "version-1"
        )
        self.assertEqual(
            versions["manifest_version_id"], "version-2"
        )
        self.assertEqual(
            manifest["artifact"]["version_id"], "version-1"
        )

        self.assertEqual(
            hashlib.sha256(
                self.client.objects[self.MANIFEST_KEY]["data"]
            ).hexdigest(),
            self.client.objects[self.MANIFEST_KEY]["sha256"],
        )

        for kind, key, version in self.client.calls:
            if kind in ("get", "retention"):
                self.assertEqual(
                    version,
                    self.client.objects[key]["version"],
                )

        self.assertEqual(
            len([
                call for call in self.client.calls
                if call[0] == "get"
            ]),
            2,
        )

    def test_corrupted_download_fails_closed(self):
        self.client.tamper_key = self.DUMP_KEY

        with self.assertRaises(RuntimeError):
            self.upload()

        self.assertFalse(self.versions.exists())
        self.assertNotIn(
            "version_id",
            json.loads(
                self.manifest.read_text()
            )["artifact"],
        )

    def test_concurrent_replacement_fails_closed(self):
        # Another writer replaces the current version with identical
        # content but different upload provenance.
        self.client.replace_after_upload_key = self.DUMP_KEY

        with self.assertRaises(RuntimeError):
            self.upload()

        self.assertFalse(self.versions.exists())
        self.assertNotIn(
            "version_id",
            json.loads(self.manifest.read_text())["artifact"],
        )

    def test_missing_version_fails_closed(self):
        self.client.missing_version_key = self.DUMP_KEY

        with self.assertRaises(RuntimeError):
            self.upload()

        self.assertFalse(self.versions.exists())

    def test_unexpected_get_version_fails_closed(self):
        self.client.wrong_response_version_key = self.DUMP_KEY

        with self.assertRaises(RuntimeError):
            self.upload()

        self.assertFalse(self.versions.exists())

    def test_incorrect_local_digest_fails_before_upload(self):
        self.args.dump_sha256 = "0" * 64

        with self.assertRaises(RuntimeError):
            self.upload()

        self.assertFalse(self.client.objects)
        self.assertFalse(self.versions.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
