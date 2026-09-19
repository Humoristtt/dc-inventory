"""Validate a selected backup manifest before creating restore resources."""
from __future__ import annotations

import re
from typing import Any


SHA = re.compile(r"[0-9a-f]{40}\Z")
IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _runtime_image(runtime: dict[str, Any], service: str) -> dict[str, str]:
    image = runtime.get(service)
    if not isinstance(image, dict):
        raise ValueError(f"missing {service} runtime provenance")
    image_id = image.get("image_id")
    revision = image.get("source_revision")
    if not isinstance(image_id, str) or IMAGE.fullmatch(image_id) is None:
        raise ValueError(f"invalid {service} image ID")
    if not isinstance(revision, str) or SHA.fullmatch(revision) is None:
        raise ValueError(f"invalid {service} source revision")
    return {"image_id": image_id, "source_revision": revision}


def application_artifacts(manifest: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Return the validated backend and web image provenance."""
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("backup manifest has no runtime provenance")
    return _runtime_image(runtime, "backend"), _runtime_image(runtime, "web")


def validate_manifest(manifest: object, manifest_key: str, prefix: str) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("backup manifest is not an object")
    if manifest.get("schema_version") != 2:
        raise ValueError("Stage15 final recovery requires manifest schema v2")
    if manifest.get("application") != "dc-inventory" or manifest.get("backup_type") != "full":
        raise ValueError("backup manifest application/type mismatch")
    if not manifest_key.startswith(prefix) or not manifest_key.endswith(".manifest.json"):
        raise ValueError("invalid manifest key")

    checkout = manifest.get("production_checkout_sha")
    if not isinstance(checkout, str) or SHA.fullmatch(checkout) is None:
        raise ValueError("backup manifest has invalid production checkout provenance")
    for field in ("alembic_head", "postgresql_tools"):
        if not isinstance(manifest.get(field), str) or not manifest[field].strip():
            raise ValueError(f"backup manifest has invalid {field}")

    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        raise ValueError("backup manifest has no artifact")
    expected_key = manifest_key.removesuffix(".manifest.json") + ".dump"
    if artifact.get("key") != expected_key:
        raise ValueError("backup dump key does not match manifest key")
    if artifact.get("format") != "pg_dump-custom":
        raise ValueError("backup dump format mismatch")
    digest = artifact.get("sha256")
    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        raise ValueError("invalid backup dump SHA-256")
    size = artifact.get("size_bytes")
    if type(size) is not int or size <= 0:
        raise ValueError("invalid backup dump size")

    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("backup manifest has no runtime provenance")
    backend, _web = application_artifacts(manifest)
    for service in ("telegram_worker", "maintenance_worker"):
        if _runtime_image(runtime, service) != backend:
            raise ValueError(f"{service} runtime does not match backend")
    if runtime.get("postgres") is not None:
        _runtime_image(runtime, "postgres")
    email = runtime.get("email_worker")
    if email is not None:
        if not isinstance(email, dict):
            raise ValueError("invalid email worker runtime")
        if email.get("state") == "disabled":
            if set(email) != {"state"}:
                raise ValueError("disabled email runtime has unexpected metadata")
        elif email.get("state") == "enabled":
            if _runtime_image(runtime, "email_worker") != backend:
                raise ValueError("email worker runtime does not match backend")
        else:
            raise ValueError("invalid email worker runtime state")
    return manifest
