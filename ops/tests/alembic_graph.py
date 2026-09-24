#!/usr/bin/env python3
"""Return the single Alembic head derived from the migration graph."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def source_alembic_heads(
    root: Path = ROOT,
) -> set[str]:
    versions = root / "backend/migrations/versions"

    revisions: set[str] = set()
    parents: set[str] = set()

    for path in versions.glob("*.py"):
        tree = ast.parse(
            path.read_text(),
            filename=str(path),
        )

        revision: str | None = None
        down_revisions: list[str] = []

        for node in tree.body:
            name: str | None = None
            value_node: ast.expr | None = None

            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.value is not None
            ):
                name = node.target.id
                value_node = node.value

            elif (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                name = node.targets[0].id
                value_node = node.value

            if name not in {
                "revision",
                "down_revision",
            }:
                continue

            if value_node is None:
                continue

            value = ast.literal_eval(value_node)

            if name == "revision":
                if isinstance(value, str):
                    revision = value
                continue

            if isinstance(value, str):
                down_revisions = [value]

            elif isinstance(value, (tuple, list)):
                down_revisions = [
                    item
                    for item in value
                    if isinstance(item, str)
                ]

            elif value is None:
                down_revisions = []

        if revision is not None:
            revisions.add(revision)
            parents.update(down_revisions)

    return revisions - parents


def single_source_alembic_head(
    root: Path = ROOT,
) -> str:
    heads = source_alembic_heads(root)

    if len(heads) != 1:
        raise RuntimeError(
            "expected exactly one source Alembic head, "
            f"got {sorted(heads)}"
        )

    return next(iter(heads))


if __name__ == "__main__":
    print(single_source_alembic_head())
