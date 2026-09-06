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

    labels = inspected["Config"].get("Labels") or {}
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

    if SHA_RE.fullmatch(checkout) is None:
        raise RuntimeError(
            f"invalid production checkout SHA: {checkout!r}"
        )

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
            "web": web,
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
