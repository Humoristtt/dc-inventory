#!/usr/bin/env python3
"""Compare approved release artifacts with collected runtime provenance."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
SERVICES = ("backend", "web", "postgres")


def require_sha(value: object, name: str) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError(f"{name}: invalid Git SHA")
    return value


def require_image_id(value: object, name: str) -> str:
    if not isinstance(value, str) or IMAGE_ID.fullmatch(value) is None:
        raise ValueError(f"{name}: invalid immutable image ID")
    return value


def require_object(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{name}: expected JSON object")
    return value


def verify(release: object, provenance: object) -> None:
    release = require_object(release, "release")
    provenance = require_object(provenance, "provenance")

    if release.get("schema_version") != 1:
        raise ValueError("release: unsupported schema version")

    if provenance.get("schema_version") != 1:
        raise ValueError("provenance: unsupported schema version")

    revision = require_sha(
        release.get("source_revision"),
        "release.source_revision",
    )

    checkout = require_sha(
        provenance.get("production_checkout_sha"),
        "provenance.production_checkout_sha",
    )

    if checkout != revision:
        raise ValueError(
            "production checkout SHA mismatch; source-only sync "
            "requires separate verification and approval"
        )

    images = require_object(release.get("images"), "release.images")
    runtime = require_object(provenance.get("runtime"), "provenance.runtime")

    if set(images) != set(SERVICES):
        raise ValueError("release: unexpected image service set")

    for service in SERVICES:
        approved = require_object(
            images[service],
            f"release.images.{service}",
        )
        actual = require_object(
            runtime.get(service),
            f"provenance.runtime.{service}",
        )

        approved_revision = require_sha(
            approved.get("source_revision"),
            f"release.{service}.source_revision",
        )
        actual_revision = require_sha(
            actual.get("source_revision"),
            f"runtime.{service}.source_revision",
        )

        approved_id = require_image_id(
            approved.get("image_id"),
            f"release.{service}.image_id",
        )
        actual_id = require_image_id(
            actual.get("image_id"),
            f"runtime.{service}.image_id",
        )

        if approved_revision != revision:
            raise ValueError(f"{service}: inconsistent release revision")

        if actual_revision != approved_revision:
            raise ValueError(f"{service}: runtime revision mismatch")

        if actual_id != approved_id:
            raise ValueError(f"{service}: runtime image ID mismatch")

    backend = require_object(runtime.get("backend"), "runtime.backend")

    for service in ("telegram_worker", "maintenance_worker"):
        worker = require_object(runtime.get(service), f"runtime.{service}")

        if worker != backend:
            raise ValueError(f"{service}: backend image mismatch")

    email = require_object(runtime.get("email_worker"), "runtime.email_worker")
    state = email.get("state")

    if state == "disabled":
        if email != {"state": "disabled"}:
            raise ValueError("email_worker: invalid disabled state")
    elif state == "enabled":
        if {
            "image_id": email.get("image_id"),
            "source_revision": email.get("source_revision"),
        } != backend:
            raise ValueError("email_worker: backend image mismatch")
    else:
        raise ValueError("email_worker: invalid state")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--runtime-provenance", type=Path, required=True)
    args = parser.parse_args()

    try:
        release = json.loads(
            args.release_manifest.read_text(encoding="utf-8")
        )
        provenance = json.loads(
            args.runtime_provenance.read_text(encoding="utf-8")
        )
        verify(release, provenance)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"RELEASE_RUNTIME_MATCH=FAIL: {exc}\n")

    print("RELEASE_RUNTIME_MATCH=PASS")


if __name__ == "__main__":
    main()
