#!/usr/bin/env python3
"""Fail-closed local PostgreSQL identity checks for full-stack acceptance."""

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ["docker", "compose", "-f", "compose.dev.yaml"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_topology(config: dict, container: dict, expected_hash: str, port: int) -> None:
    labels = container["Config"]["Labels"]

    ports = [
        item
        for item in config["services"]["postgres"]["ports"]
        if int(item["target"]) == 5432
    ]

    bindings = container["NetworkSettings"]["Ports"].get("5432/tcp") or []

    require(config.get("name") == "dc-inventory-dev", "wrong Compose project")
    require(container["State"]["Running"], "PostgreSQL container is stopped")
    require(
        labels.get("com.docker.compose.project") == "dc-inventory-dev",
        "wrong container project",
    )
    require(
        labels.get("com.docker.compose.service") == "postgres",
        "wrong container service",
    )
    require(
        labels.get("com.docker.compose.config-hash") == expected_hash,
        "PostgreSQL container configuration differs",
    )
    require(len(ports) == 1, "unexpected configured PostgreSQL ports")
    require(len(bindings) == 1, "unexpected runtime PostgreSQL bindings")

    require(
        ports[0].get("host_ip") == "127.0.0.1"
        and bindings[0]["HostIp"] == "127.0.0.1",
        "PostgreSQL must bind to loopback only",
    )

    require(
        int(ports[0]["published"]) == port
        and int(bindings[0]["HostPort"]) == port,
        "PostgreSQL host port mismatch",
    )


def validate_target(url: str, database: str, port: int) -> None:
    require(
        re.fullmatch(r"dc_inventory_fullstack_[0-9]{14}_[0-9]+", database) is not None,
        "invalid disposable database name",
    )

    parsed = urlsplit(url)

    require(parsed.scheme == "postgresql+asyncpg", "wrong database driver")
    require(parsed.hostname == "127.0.0.1", "database host is not loopback")
    require(parsed.port == port, "database URL port mismatch")
    require(parsed.path == f"/{database}", "database URL name mismatch")
    require(not parsed.query and not parsed.fragment, "unexpected database URL parameters")


def run(*args: str) -> str:
    return subprocess.check_output(
        args,
        text=True,
        stderr=subprocess.PIPE,
    ).strip()


def check_topology(port: int) -> None:
    config = json.loads(run(*COMPOSE, "config", "--format", "json"))

    ids = run(*COMPOSE, "ps", "-q", "postgres").splitlines()
    require(len(ids) == 1, "expected exactly one PostgreSQL container")

    container = json.loads(run("docker", "inspect", ids[0]))[0]
    expected_hash = run(*COMPOSE, "config", "--hash", "postgres").split()[-1]

    validate_topology(config, container, expected_hash, port)


async def check_challenge(database: str, nonce: str) -> None:
    sys.path.insert(0, str(ROOT / "backend"))

    from sqlalchemy import text

    from app.db.engine import create_engine

    engine = create_engine(application_name="dc-inventory-fullstack-premigration")

    try:
        async with engine.connect() as connection:
            actual_database = await connection.scalar(
                text("SELECT current_database()")
            )
            actual_nonce = await connection.scalar(
                text("SELECT token FROM cp15_fullstack_probe")
            )

        require(actual_database == database, "connected to wrong database")
        require(actual_nonce == nonce, "PostgreSQL instance challenge mismatch")
    finally:
        await engine.dispose()


def main() -> None:
    require(
        len(sys.argv) == 2 and sys.argv[1] in ("topology", "verify"),
        "expected topology or verify",
    )

    port = int(os.environ.get("POSTGRES_DEV_PORT", "55432"))

    if sys.argv[1] == "topology":
        check_topology(port)
        print("FULLSTACK_POSTGRES_TOPOLOGY=PASS")
        return

    if sys.argv[1] == "verify":
        database = os.environ["TEST_DB"]
        nonce = os.environ["FULLSTACK_DB_NONCE"]

        require(
            re.fullmatch(r"[0-9a-f]{64}", nonce) is not None,
            "invalid database challenge",
        )
        validate_target(os.environ["DATABASE_URL"], database, port)

        try:
            asyncio.run(check_challenge(database, nonce))
        except Exception:
            raise SystemExit(
                "STOP: pre-migration PostgreSQL challenge verification failed"
            ) from None

        print("FULLSTACK_PREMIGRATION_DATABASE=PASS")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(
            f"STOP: full-stack database guard failed: {type(exc).__name__}"
        ) from None
