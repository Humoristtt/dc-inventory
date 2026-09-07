#!/usr/bin/env python3

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

spec = (
    ROOT / "frontend/e2e/fullstack.spec.ts"
).read_text()

package = json.loads(
    (ROOT / "frontend/package.json").read_text()
)

workflow = (
    ROOT / ".github/workflows/ci.yml"
).read_text()


assert package["scripts"]["test:e2e"] == (
    "playwright test e2e/warehouse-v2.spec.ts"
)

assert package["scripts"]["test:e2e:fullstack"] == (
    "playwright test "
    "e2e/fullstack.spec.ts "
    "--project=desktop-admin"
)

assert "createHmac" in spec
assert "/api/auth/telegram" in spec
assert "/api/catalog/categories" in spec
assert "page.waitForResponse" in spec

# Telegram WebApp context may be injected, but API transport
# itself must never be mocked in this integrated scenario.
assert "page.route(" not in spec

for required in (
    "Full-stack browser acceptance",
    "Verify full-stack database side effects",
    "FULLSTACK_TELEGRAM_BOT_TOKEN",
    "FULLSTACK_TELEGRAM_USER_ID",
    "npm run test:e2e:fullstack",
    "FULLSTACK_DATABASE_SIDE_EFFECTS=PASS",
):
    assert required in workflow, required

print("FULLSTACK_E2E_CONTRACT=PASS")
