#!/usr/bin/env python3
"""Validate local and explicit Unix ingress Compose configurations."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOCKET_DIR = "/run/dc-inventory"


def render(*, unix: bool, directory: str | None = None):
    command = [
        "docker",
        "compose",
        "--env-file",
        "/dev/null",
        "-f",
        "compose.yaml",
    ]

    if unix:
        command.extend(["-f", "compose.ingress-unix.yaml"])

    command.extend(["config", "--format", "json"])

    environment = os.environ.copy()
    environment.pop("INGRESS_HOST_DIR", None)

    # Synthetic interpolation values: never read the production .env.
    environment.update(
        POSTGRES_DB="dc_inventory_test",
        POSTGRES_USER="ci_test",
        POSTGRES_PASSWORD="ci-only-placeholder",
        POSTGRES_RUNTIME_USER="ci_runtime",
        POSTGRES_RUNTIME_PASSWORD="ci-only-placeholder",
        POSTGRES_TELEGRAM_WORKER_USER="ci_telegram",
        POSTGRES_TELEGRAM_WORKER_PASSWORD="ci-only-placeholder",
        POSTGRES_EMAIL_WORKER_USER="ci_email",
        POSTGRES_EMAIL_WORKER_PASSWORD="ci-only-placeholder",
        POSTGRES_MAINTENANCE_USER="ci_maintenance",
        POSTGRES_MAINTENANCE_PASSWORD="ci-only-placeholder",
    )

    if directory is not None:
        environment["INGRESS_HOST_DIR"] = directory

    return subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class IngressComposeTests(unittest.TestCase):
    def test_default_web_has_writable_private_socket_directory(self):
        result = render(unix=False)
        self.assertEqual(result.returncode, 0, "base Compose config failed")

        web = json.loads(result.stdout)["services"]["web"]

        self.assertTrue(web["read_only"])

        tmpfs = web.get("tmpfs", [])
        self.assertTrue(
            any(
                SOCKET_DIR in str(entry)
                and "uid=101" in str(entry)
                and "gid=101" in str(entry)
                for entry in tmpfs
            ),
            tmpfs,
        )

        self.assertFalse(
            any(
                volume.get("target") == SOCKET_DIR
                for volume in web.get("volumes", [])
            )
        )

        ports = web.get("ports", [])
        self.assertEqual(len(ports), 1, ports)
        self.assertEqual(
            ports[0].get("host_ip"),
            "127.0.0.1",
            "Default web must not publish a public TCP port",
        )
        self.assertEqual(ports[0].get("target"), 8080)

    def test_unix_override_requires_explicit_host_directory(self):
        result = render(unix=True)
        self.assertNotEqual(result.returncode, 0)

    def test_unix_override_replaces_tmpfs_and_removes_tcp_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary).resolve()
            directory.chmod(0o750)

            result = render(
                unix=True,
                directory=str(directory),
            )

            self.assertEqual(
                result.returncode,
                0,
                "Unix override Compose config failed",
            )

            web = json.loads(result.stdout)["services"]["web"]

            self.assertFalse(web.get("ports"))
            self.assertTrue(
                web["read_only"],
                "Unix override must preserve read-only root filesystem",
            )
            self.assertEqual(web.get("tmpfs"), ["/tmp"])

            mounts = [
                volume
                for volume in web.get("volumes", [])
                if volume.get("target") == SOCKET_DIR
            ]

            self.assertEqual(len(mounts), 1)

            mount = mounts[0]

            self.assertEqual(mount["type"], "bind")
            self.assertEqual(mount["source"], str(directory))
            self.assertFalse(mount.get("read_only", False))
            self.assertFalse(mount["bind"]["create_host_path"])


if __name__ == "__main__":
    unittest.main()
