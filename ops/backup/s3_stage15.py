#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config


REQUIRED_ENV = {
    "S3_ENDPOINT",
    "S3_REGION",
    "S3_ADDRESSING_STYLE",
    "S3_BUCKET",
    "S3_PREFIX",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_CA_BUNDLE",
}


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        key, separator, value = line.partition("=")

        if not separator:
            raise RuntimeError(f"Invalid env line for key {key!r}")

        values[key] = value

    missing = sorted(REQUIRED_ENV - values.keys())

    if missing:
        raise RuntimeError(
            "Missing S3 configuration keys: " + ", ".join(missing)
        )

    return values


def make_client(env: dict[str, str]):
    return boto3.client(
        "s3",
        endpoint_url=env["S3_ENDPOINT"],
        region_name=env["S3_REGION"],
        aws_access_key_id=env["S3_ACCESS_KEY"],
        aws_secret_access_key=env["S3_SECRET_KEY"],
        verify=env["S3_CA_BUNDLE"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": env["S3_ADDRESSING_STYLE"]},
        ),
    )


def validate_storage(client, env: dict[str, str]) -> None:
    bucket = env["S3_BUCKET"]
    prefix = env["S3_PREFIX"].rstrip("/") + "/"

    client.head_bucket(Bucket=bucket)
    client.list_objects_v2(
        Bucket=bucket,
        Prefix=prefix,
        MaxKeys=1,
    )

    lock_response = client.get_object_lock_configuration(
        Bucket=bucket
    )
    lock = lock_response.get("ObjectLockConfiguration", {})

    if lock.get("ObjectLockEnabled") != "Enabled":
        raise RuntimeError("S3 Object Lock is not enabled")

    retention = lock.get("Rule", {}).get(
        "DefaultRetention",
        {},
    )

    if retention.get("Mode") != "GOVERNANCE":
        raise RuntimeError(
            "Default Object Lock mode is not GOVERNANCE"
        )

    if retention.get("Days") != 7:
        raise RuntimeError(
            "Default Object Lock retention is not 7 days"
        )

    lifecycle = client.get_bucket_lifecycle_configuration(
        Bucket=bucket
    )
    rules = {
        rule["ID"]: rule
        for rule in lifecycle.get("Rules", [])
    }

    current = rules.get("postgres-current-expire-30d")

    if not current:
        raise RuntimeError(
            "30-day current-version lifecycle rule is missing"
        )

    if current.get("Status") != "Enabled":
        raise RuntimeError(
            "30-day current-version lifecycle rule is disabled"
        )

    if current.get("Expiration", {}).get("Days") != 30:
        raise RuntimeError(
            "Current-version lifecycle retention is not 30 days"
        )

    noncurrent = rules.get(
        "postgres-noncurrent-expire-1d"
    )

    if not noncurrent:
        raise RuntimeError(
            "Noncurrent-version lifecycle rule is missing"
        )

    if noncurrent.get("Status") != "Enabled":
        raise RuntimeError(
            "Noncurrent-version lifecycle rule is disabled"
        )

    noncurrent_days = noncurrent.get(
        "NoncurrentVersionExpiration",
        {},
    ).get("NoncurrentDays")

    if noncurrent_days != 1:
        raise RuntimeError(
            "Noncurrent-version lifecycle retention is not 1 day"
        )

    markers = rules.get(
        "postgres-expired-delete-markers"
    )

    if not markers:
        raise RuntimeError(
            "Expired delete-marker lifecycle rule is missing"
        )

    if markers.get("Status") != "Enabled":
        raise RuntimeError(
            "Expired delete-marker lifecycle rule is disabled"
        )

    marker_cleanup = markers.get(
        "Expiration",
        {},
    ).get("ExpiredObjectDeleteMarker")

    if not marker_cleanup:
        raise RuntimeError(
            "Expired delete-marker cleanup is not enabled"
        )

    print("S3_HEAD_BUCKET=PASS")
    print("S3_LIST_PREFIX=PASS")
    print("S3_OBJECT_LOCK=GOVERNANCE_7D_PASS")
    print("S3_RETENTION_30D=PASS")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        while True:
            chunk = source.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def verify_object(
    client,
    *,
    bucket: str,
    key: str,
    source: Path,
    expected_sha256: str,
) -> None:
    head = client.head_object(
        Bucket=bucket,
        Key=key,
    )

    local_size = source.stat().st_size
    remote_size = head["ContentLength"]

    if remote_size != local_size:
        raise RuntimeError(
            f"Remote size mismatch for {key}: "
            f"{remote_size} != {local_size}"
        )

    remote_sha256 = head.get(
        "Metadata",
        {},
    ).get("sha256")

    if remote_sha256 != expected_sha256:
        raise RuntimeError(
            f"Remote SHA-256 metadata mismatch for {key}"
        )

    response = client.get_object(
        Bucket=bucket,
        Key=key,
    )

    body = response["Body"]
    digest = hashlib.sha256()

    try:
        while True:
            chunk = body.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)
    finally:
        body.close()

    downloaded_sha256 = digest.hexdigest()

    if downloaded_sha256 != expected_sha256:
        raise RuntimeError(
            f"Remote object SHA-256 mismatch for {key}: "
            f"{downloaded_sha256} != {expected_sha256}"
        )

    retention = client.get_object_retention(
        Bucket=bucket,
        Key=key,
    ).get("Retention", {})

    if retention.get("Mode") != "GOVERNANCE":
        raise RuntimeError(
            f"Object {key} is not protected by "
            "GOVERNANCE retention"
        )

    retain_until = retention.get("RetainUntilDate")

    if retain_until is None:
        raise RuntimeError(
            f"Object {key} has no retention date"
        )

    minimum = (
        datetime.now(timezone.utc)
        + timedelta(days=6)
    )

    if retain_until <= minimum:
        raise RuntimeError(
            f"Object {key} retention is unexpectedly short: "
            f"{retain_until.isoformat()}"
        )

    print(
        f"[OK] {key} "
        f"size={remote_size} "
        f"sha256={expected_sha256} "
        f"retain_until={retain_until.isoformat()}"
    )


def upload_object(
    client,
    *,
    bucket: str,
    key: str,
    source: Path,
    sha256: str,
    content_type: str,
) -> None:
    client.upload_file(
        str(source),
        bucket,
        key,
        ExtraArgs={
            "ContentType": content_type,
            "Metadata": {
                "sha256": sha256,
            },
        },
    )

    verify_object(
        client,
        bucket=bucket,
        key=key,
        source=source,
        expected_sha256=sha256,
    )


def command_preflight(args: argparse.Namespace) -> None:
    env = load_env(args.env)
    client = make_client(env)

    validate_storage(client, env)

    print("STAGE15A_S3_PREFLIGHT=PASS")


def command_upload(args: argparse.Namespace) -> None:
    env = load_env(args.env)
    client = make_client(env)

    validate_storage(client, env)

    bucket = env["S3_BUCKET"]
    prefix = env["S3_PREFIX"].rstrip("/") + "/"

    if not args.dump_key.startswith(prefix):
        raise RuntimeError(
            "Dump key is outside configured S3 prefix"
        )

    if not args.manifest_key.startswith(prefix):
        raise RuntimeError(
            "Manifest key is outside configured S3 prefix"
        )

    actual_dump_sha256 = sha256_file(args.dump)

    if actual_dump_sha256 != args.dump_sha256:
        raise RuntimeError(
            "Local dump SHA-256 changed before upload"
        )

    manifest_sha256 = sha256_file(args.manifest)

    upload_object(
        client,
        bucket=bucket,
        key=args.dump_key,
        source=args.dump,
        sha256=args.dump_sha256,
        content_type="application/octet-stream",
    )

    upload_object(
        client,
        bucket=bucket,
        key=args.manifest_key,
        source=args.manifest,
        sha256=manifest_sha256,
        content_type="application/json",
    )

    print("STAGE15A_REMOTE_VERIFICATION=PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument(
        "--env",
        type=Path,
        default=Path(
            "/etc/dc-inventory/stage15-backup.env"
        ),
    )
    preflight.set_defaults(func=command_preflight)

    upload = subparsers.add_parser("upload")
    upload.add_argument(
        "--env",
        type=Path,
        default=Path(
            "/etc/dc-inventory/stage15-backup.env"
        ),
    )
    upload.add_argument(
        "--dump",
        type=Path,
        required=True,
    )
    upload.add_argument(
        "--manifest",
        type=Path,
        required=True,
    )
    upload.add_argument(
        "--dump-key",
        required=True,
    )
    upload.add_argument(
        "--manifest-key",
        required=True,
    )
    upload.add_argument(
        "--dump-sha256",
        required=True,
    )
    upload.set_defaults(func=command_upload)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
