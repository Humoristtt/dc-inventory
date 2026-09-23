#!/usr/bin/env python3
"""Verify the production host direct-ingress contract without changing it."""

from __future__ import annotations

import json
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "ops" / "host_ingress"

SITE_SOURCE = (
    SOURCE_ROOT
    / "nginx"
    / "dc-inventory-direct.conf"
)

HOOK_SOURCE = (
    SOURCE_ROOT
    / "certbot"
    / "reload-nginx"
)

SITE = Path(
    "/etc/nginx/sites-available/"
    "dc-inventory-direct"
)

ENABLED = Path(
    "/etc/nginx/sites-enabled/"
    "dc-inventory-direct"
)

HOOK = Path(
    "/etc/letsencrypt/renewal-hooks/"
    "deploy/reload-nginx"
)

RENEWAL = Path(
    "/etc/letsencrypt/renewal/"
    "app.spik-inventory.ru.conf"
)

ACME_ROOT = Path(
    "/var/www/letsencrypt"
)

INGRESS_DIR = Path(
    "/var/lib/dc-inventory-ingress"
)

INGRESS_SOCKET = (
    INGRESS_DIR
    / "ingress.sock"
)

CERT = Path(
    "/etc/letsencrypt/live/"
    "app.spik-inventory.ru/fullchain.pem"
)

KEY = Path(
    "/etc/letsencrypt/live/"
    "app.spik-inventory.ru/privkey.pem"
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(*args: str) -> str:
    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        detail = (
            result.stderr
            or result.stdout
        ).strip()

        fail(
            f"{' '.join(args)} failed: "
            f"{detail}"
        )

    return result.stdout.strip()


def require_exact_file(
    source: Path,
    installed: Path,
    mode: int,
) -> None:
    if not source.is_file():
        fail(
            f"source file missing: "
            f"{source}"
        )

    if not installed.is_file():
        fail(
            f"installed file missing: "
            f"{installed}"
        )

    if (
        source.read_bytes()
        != installed.read_bytes()
    ):
        fail(
            f"installed file drift: "
            f"{installed}"
        )

    actual_mode = stat.S_IMODE(
        installed.stat().st_mode
    )

    if actual_mode != mode:
        fail(
            f"{installed}: mode "
            f"{actual_mode:04o}, "
            f"expected {mode:04o}"
        )


def require_service(unit: str) -> None:
    if (
        run(
            "systemctl",
            "is-enabled",
            unit,
        )
        != "enabled"
    ):
        fail(
            f"{unit}: not enabled"
        )

    if (
        run(
            "systemctl",
            "is-active",
            unit,
        )
        != "active"
    ):
        fail(
            f"{unit}: not active"
        )


def main() -> int:
    require_exact_file(
        SITE_SOURCE,
        SITE,
        0o644,
    )

    require_exact_file(
        HOOK_SOURCE,
        HOOK,
        0o755,
    )

    if not ENABLED.is_symlink():
        fail(
            "enabled site is not "
            f"a symlink: {ENABLED}"
        )

    if ENABLED.resolve() != SITE:
        fail(
            "enabled site points to "
            f"{ENABLED.resolve()}, "
            f"expected {SITE}"
        )

    nginx_main = Path(
        "/etc/nginx/nginx.conf"
    ).read_text()

    if "user www-data;" not in nginx_main:
        fail(
            "host nginx worker user "
            "is not www-data"
        )

    ingress = INGRESS_DIR.stat()

    if (
        ingress.st_uid,
        ingress.st_gid,
    ) != (101, 33):
        fail(
            "ingress directory owner "
            f"mismatch: "
            f"{ingress.st_uid}:"
            f"{ingress.st_gid}, "
            "expected 101:33"
        )

    if (
        stat.S_IMODE(ingress.st_mode)
        != 0o750
    ):
        fail(
            "ingress directory mode "
            "is not 0750"
        )

    socket_stat = (
        INGRESS_SOCKET.stat()
    )

    if not stat.S_ISSOCK(
        socket_stat.st_mode
    ):
        fail(
            "not a Unix socket: "
            f"{INGRESS_SOCKET}"
        )

    if socket_stat.st_uid != 101:
        fail(
            "ingress socket uid "
            f"{socket_stat.st_uid}, "
            "expected 101"
        )

    if (
        stat.S_IMODE(
            socket_stat.st_mode
        )
        != 0o666
    ):
        fail(
            "ingress socket mode "
            "is not 0666"
        )

    acme = ACME_ROOT.stat()

    if (
        acme.st_uid,
        acme.st_gid,
    ) != (0, 0):
        fail(
            "ACME webroot is not "
            "owned by root:root"
        )

    if (
        stat.S_IMODE(acme.st_mode)
        != 0o755
    ):
        fail(
            "ACME webroot mode "
            "is not 0755"
        )

    for path in (
        CERT,
        KEY,
        RENEWAL,
    ):
        if not path.exists():
            fail(
                "required certificate "
                f"path missing: {path}"
            )

    renewal = RENEWAL.read_text()

    required_renewal = (
        "authenticator = webroot",
        (
            "server = "
            "https://acme-v02."
            "api.letsencrypt.org/"
            "directory"
        ),
        "key_type = ecdsa",
        (
            "webroot_path = "
            "/var/www/letsencrypt,"
        ),
    )

    for line in required_renewal:
        if line not in renewal:
            fail(
                "renewal contract "
                f"missing: {line}"
            )

    require_service("nginx")
    require_service("certbot.timer")

    run(
        "/usr/sbin/nginx",
        "-t",
    )

    port_bindings = json.loads(
        run(
            "docker",
            "inspect",
            "dc-inventory-web-1",
            "--format",
            (
                "{{json "
                ".HostConfig.PortBindings}}"
            ),
        )
    )

    if port_bindings:
        fail(
            "web container publishes "
            f"host ports: {port_bindings}"
        )

    health = run(
        "curl",
        "-fsS",
        "--resolve",
        (
            "app.spik-inventory.ru:"
            "443:127.0.0.1"
        ),
        (
            "https://"
            "app.spik-inventory.ru/"
            "healthz"
        ),
    )

    if health != "ok":
        fail(
            "unexpected /healthz "
            f"response: {health!r}"
        )

    ready = json.loads(
        run(
            "curl",
            "-fsS",
            "--resolve",
            (
                "app.spik-inventory.ru:"
                "443:127.0.0.1"
            ),
            (
                "https://"
                "app.spik-inventory.ru/"
                "api/health/ready"
            ),
        )
    )

    if ready != {
        "status": "ready"
    }:
        fail(
            "unexpected ready "
            f"response: {ready!r}"
        )

    print(
        "HOST_INGRESS_FILES=PASS"
    )
    print(
        "HOST_INGRESS_PERMISSIONS=PASS"
    )
    print(
        "HOST_INGRESS_SERVICES=PASS"
    )
    print(
        "HOST_INGRESS_RUNTIME=PASS"
    )
    print(
        "HOST_DIRECT_INGRESS=PASS"
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(
            "HOST_DIRECT_INGRESS=FAIL: "
            f"{exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
