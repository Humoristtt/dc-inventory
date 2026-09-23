#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


REVISION_LABEL = "org.opencontainers.image.revision"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def command(root: Path, env_file: str | None, *args: str) -> list[str]:
    result = ["docker", "compose"]

    if env_file is not None:
        result.extend(["--env-file", env_file])

    result.extend(args)
    return result


def run(
    root: Path,
    env_file: str | None,
    *args: str,
) -> str:
    return subprocess.run(
        command(root, env_file, *args),
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()


def collect(
    root: Path,
    env_file: str | None,
    service: str,
) -> dict[str, str]:
    container_id = run(
        root,
        env_file,
        "ps",
        "-q",
        service,
    )

    if not container_id:
        raise RuntimeError(
            f"{service}: running container was not found"
        )

    inspected = json.loads(
        subprocess.run(
            ["docker", "inspect", container_id],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
    )[0]

    if not inspected["State"]["Running"]:
        raise RuntimeError(
            f"{service}: container is not running"
        )

    image_id = inspected["Image"]

    if IMAGE_RE.fullmatch(image_id) is None:
        raise RuntimeError(
            f"{service}: invalid immutable image ID {image_id!r}"
        )

    # The immutable image is authoritative; container labels can be overridden.
    image_metadata = json.loads(subprocess.run(
        ["docker", "image", "inspect", image_id], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout)[0]
    labels = image_metadata["Config"].get("Labels") or {}
    revision = labels.get(REVISION_LABEL, "")

    if SHA_RE.fullmatch(revision) is None:
        raise RuntimeError(
            f"{service}: missing/invalid {REVISION_LABEL}: "
            f"{revision!r}"
        )

    return {
        "image_id": image_id,
        "source_revision": revision,
    }


def email_delivery_enabled(
    root: Path,
    env_file: str | None,
) -> bool:
    container_id = run(root, env_file, "ps", "-q", "backend")
    if not container_id:
        raise RuntimeError("backend: running container was not found")
    inspected = json.loads(
        subprocess.run(
            ["docker", "inspect", container_id],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout
    )[0]
    values = {
        entry.split("=", 1)[0]: entry.split("=", 1)[1]
        for entry in inspected["Config"].get("Env", [])
        if "=" in entry
    }
    raw = values.get("EMAIL_DELIVERY_ENABLED")
    if raw not in {"true", "false"}:
        raise RuntimeError("backend: EMAIL_DELIVERY_ENABLED must be explicitly true or false")
    return raw == "true"


def verify_checkout(root: Path, claimed_sha: str) -> None:
    """Verify the reported checkout against the actual Git HEAD."""
    if SHA_RE.fullmatch(claimed_sha) is None:
        raise RuntimeError(f"invalid production checkout SHA: {claimed_sha!r}")

    actual_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
    ).strip()

    if actual_sha != claimed_sha:
        raise RuntimeError(
            "production checkout SHA mismatch: "
            f"claimed={claimed_sha}, actual={actual_sha}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--production-checkout-sha",
        required=True,
    )
    parser.add_argument("--env-file")
    args = parser.parse_args()

    checkout = args.production_checkout_sha

    verify_checkout(args.root, checkout)

    backend = collect(
        args.root,
        args.env_file,
        "backend",
    )
    telegram = collect(
        args.root,
        args.env_file,
        "telegram-worker",
    )
    maintenance = collect(
        args.root,
        args.env_file,
        "maintenance-worker",
    )
    web = collect(
        args.root,
        args.env_file,
        "web",
    )

    postgres = collect(args.root, args.env_file, "postgres")

    if email_delivery_enabled(args.root, args.env_file):
        email = collect(args.root, args.env_file, "email-worker")
        if email != backend:
            raise RuntimeError("email-worker runtime does not match backend runtime")
        email_worker: dict[str, str] = {"state": "enabled", **email}
    else:
        if run(args.root, args.env_file, "ps", "-q", "email-worker"):
            raise RuntimeError("email-worker is running while email delivery is disabled")
        email_worker = {"state": "disabled"}

    if telegram != backend:
        raise RuntimeError(
            "telegram-worker runtime does not match backend runtime"
        )

    if maintenance != backend:
        raise RuntimeError(
            "maintenance-worker runtime does not match backend runtime"
        )

    payload = {
        "schema_version": 1,
        "production_checkout_sha": checkout,
        "runtime": {
            "backend": backend,
            "telegram_worker": telegram,
            "maintenance_worker": maintenance,
            "email_worker": email_worker,
            "web": web,
            "postgres": postgres,
        },
    }

    args.output.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    os.chmod(args.output, 0o600)

    print("RUNTIME_PROVENANCE=PASS")


if __name__ == "__main__":
    main()
