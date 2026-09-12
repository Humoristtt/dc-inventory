#!/usr/bin/env python3

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

backend_app = "\n".join(
    path.read_text()
    for path in (
        ROOT / "backend/app"
    ).rglob("*.py")
)

dependencies = (
    ROOT
    / "backend/app/modules/auth/dependencies.py"
).read_text()

rbac_docs = (
    ROOT / "docs/RBAC_PROCUREMENT.md"
).read_text()

config = (
    ROOT / "backend/app/core/config.py"
).read_text()

stale_tokens = (
    "bootstrap_admin",
    "get_admin_context",
    "TelegramAdminAuthorizationError",
    "_require_approved_admin",
    "_load_approved_admin",
    "_enqueue_admin_buttons_clear",
    "next_admin_telegram_user_id",
    '"Admin web console"',
)

for token in stale_tokens:
    assert token not in backend_app, token

assert not any(
    line.startswith("Admin = Annotated[")
    for line in dependencies.splitlines()
)
assert (
    "configured recovery/admin identity"
    not in rbac_docs
)

assert "admin_telegram_user_id" in config
assert "ADMIN_TELEGRAM_USER_ID" in (
    ROOT / "compose.yaml"
).read_text()
assert (
    "singleton recovery OWNER"
    in config
)

print("NAMING_CONTRACT=PASS")
