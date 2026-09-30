#!/usr/bin/env python3
"""Build a clean checkout into unused revision tags; never deploy or replace a release."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICES = {"backend": "BACKEND_IMAGE", "web": "WEB_IMAGE", "postgres": "POSTGRES_IMAGE"}


def release_refs(revision: str) -> dict[str, str]:
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("release revision must be a full Git SHA")
    return {variable: f"dc-inventory-{service}:{revision}" for service, variable in SERVICES.items()}


def output(*args: str) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def validate_release_env(env_file: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "ops" / "validate_env_file.py"),
            "--production",
            str(env_file.resolve()),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "production env validation failed"
        raise RuntimeError(
            "release environment validation failed:\n"
            + detail
        )


def verified_image(
    service: str,
    reference: str,
    revision: str,
) -> dict[str, object]:
    metadata = json.loads(
        output(
            "docker",
            "image",
            "inspect",
            reference,
            "--format",
            "{{json .}}",
        )
    )
    if (
        metadata["Config"]["Labels"].get(
            "org.opencontainers.image.revision"
        )
        != revision
    ):
        raise RuntimeError(
            f"{service}: revision mismatch"
        )

    image_id = metadata["Id"]
    if (
        re.fullmatch(
            r"sha256:[0-9a-f]{64}",
            image_id,
        )
        is None
    ):
        raise RuntimeError(
            f"{service}: invalid image ID"
        )

    return {
        "reference": reference,
        "image_id": image_id,
        "source_revision": revision,
        "repo_digests": metadata.get(
            "RepoDigests",
            [],
        ),
    }


def build(env_file: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"release output already exists: {destination}")
    if output("git", "status", "--porcelain"):
        raise RuntimeError("release build requires a clean checkout")
    revision = output("git", "rev-parse", "HEAD")
    refs = release_refs(revision)
    # Check the daemon first: a failed inspect must not mask an unavailable daemon.
    output("docker", "info", "--format", "{{.ServerVersion}}")
    existing = set(
        output(
            "docker",
            "image",
            "ls",
            "--format",
            "{{.Repository}}:{{.Tag}}",
        ).splitlines()
    )

    retained: dict[str, dict[str, object]] = {}
    missing: list[str] = []

    for service, variable in SERVICES.items():
        reference = refs[variable]
        if reference in existing:
            retained[service] = verified_image(
                service,
                reference,
                revision,
            )
        else:
            missing.append(service)

    validate_release_env(env_file)
    environment = {**os.environ, **refs, "APP_REVISION": revision}

    if missing:
        subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(env_file.resolve()),
                "-f",
                "compose.yaml",
                "build",
                *missing,
            ],
            cwd=ROOT,
            env=environment,
            check=True,
        )

    images: dict[str, dict[str, object]] = {}
    for service, variable in SERVICES.items():
        images[service] = retained.get(
            service
        ) or verified_image(
            service,
            refs[variable],
            revision,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".release-", dir=destination.parent) as staging:
        staged = Path(staging)
        (staged / "release.json").write_text(json.dumps(
            {"schema_version": 1, "source_revision": revision, "images": images}, indent=2) + "\n")
        (staged / "release.env").write_text(
            f"APP_REVISION={revision}\n" + "".join(f"{key}={value}\n" for key, value in refs.items()))
        if destination.exists():
            raise FileExistsError(f"release output already exists: {destination}")
        staged.rename(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.env_file, args.output)


if __name__ == "__main__":
    main()
