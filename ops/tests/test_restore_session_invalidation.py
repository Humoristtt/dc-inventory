#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "ops/recovery/rehearse_restore.sh"

source = SCRIPT.read_text()

assert (
    "RESTORE_AUTH_SESSIONS_INVALIDATED=PASS"
    in source
), "restore must explicitly invalidate restored auth sessions"

assert (
    "auth_sessions" in source
), "restore session invalidation must operate on auth_sessions"

assert (
    "UPDATE auth_sessions" in source
    or "DELETE FROM auth_sessions" in source
), "restored sessions must be revoked or removed"

print(
    "CP01_RESTORE_SESSION_INVALIDATION=PASS"
)
