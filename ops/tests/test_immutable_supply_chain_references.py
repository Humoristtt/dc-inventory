#!/usr/bin/env python3
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

ACTION_USE_PATTERN = re.compile(
    r"^\s*(?:-\s+)?uses:\s+(?P<spec>\S+)",
    flags=re.MULTILINE,
)
PINNED_ACTION_REF = re.compile(r"^[0-9a-f]{40}$")
PINNED_IMAGE_REF = re.compile(r"@sha256:[0-9a-f]{64}$")

LOCAL_IMAGE_REFS = {
    "${BACKEND_IMAGE:-dc-inventory-backend:local}",
    "${WEB_IMAGE:-dc-inventory-web:local}",
    "${POSTGRES_IMAGE:-dc-inventory-postgres:local}",
}


def action_references(workflow: str) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []

    for match in ACTION_USE_PATTERN.finditer(workflow):
        spec = match.group("spec")

        if spec.startswith("./"):
            continue

        if spec.startswith("docker://"):
            raise RuntimeError(
                "docker:// action references must be reviewed as immutable image references"
            )

        if "@" not in spec:
            raise RuntimeError(
                f"external GitHub Action reference has no ref: {spec}"
            )

        name, ref = spec.rsplit("@", 1)
        references.append((name, ref))

    return references


def image_references(workflow: str) -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []

    for filename in (
        "backend/Dockerfile",
        "frontend/Dockerfile",
    ):
        source = ROOT / filename

        for line in source.read_text().splitlines():
            stripped = line.strip()

            if stripped.startswith("FROM "):
                references.append(
                    (filename, stripped.split()[1])
                )

    for filename in (
        "compose.yaml",
        "compose.dev.yaml",
    ):
        source = ROOT / filename

        for line in source.read_text().splitlines():
            match = re.match(
                r"^\s*image:\s+(\S+)\s*$",
                line,
            )

            if match:
                references.append(
                    (filename, match.group(1))
                )

    for line in workflow.splitlines():
        match = re.match(
            r"^\s*image:\s+(\S+)\s*$",
            line,
        )

        if match:
            references.append(
                (
                    ".github/workflows/ci.yml",
                    match.group(1),
                )
            )

    return references


def is_local_image(image: str) -> bool:
    return (
        image.startswith("dc-inventory-")
        or image in LOCAL_IMAGE_REFS
    )


def assert_parser_regression() -> None:
    pinned = "a" * 40
    probe = f"""
steps:
  - uses: actions/checkout@{pinned}
  - name: Named action step
    uses: aquasecurity/trivy-action@v0.36.0
"""

    references = action_references(probe)

    if references != [
        ("actions/checkout", pinned),
        ("aquasecurity/trivy-action", "v0.36.0"),
    ]:
        raise RuntimeError(
            "action reference parser does not cover both anonymous and named steps"
        )

    mutable = [
        f"{name}@{ref}"
        for name, ref in references
        if PINNED_ACTION_REF.fullmatch(ref) is None
    ]

    if mutable != ["aquasecurity/trivy-action@v0.36.0"]:
        raise RuntimeError(
            "named-step mutable action regression probe was not detected"
        )


assert_parser_regression()

workflow = WORKFLOW.read_text()

action_refs = action_references(workflow)
mutable_actions = [
    f"{name}@{ref}"
    for name, ref in action_refs
    if PINNED_ACTION_REF.fullmatch(ref) is None
]

image_refs = image_references(workflow)
mutable_images = [
    f"{source}:{image}"
    for source, image in image_refs
    if not is_local_image(image)
    and PINNED_IMAGE_REF.search(image) is None
]

if mutable_actions:
    print(
        "Mutable GitHub Action references:",
        *mutable_actions,
        sep="\n",
    )

if mutable_images:
    print(
        "Mutable external image references:",
        *mutable_images,
        sep="\n",
    )

if mutable_actions or mutable_images:
    raise SystemExit(1)

print(
    "IMMUTABLE_SUPPLY_CHAIN_GUARD=PASS "
    f"actions={len(action_refs)} images={len(image_refs)}"
)
