set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

EXPECTED_ALEMBIC_HEAD="$(
  python3 ops/tests/alembic_graph.py
)"
test -n "$EXPECTED_ALEMBIC_HEAD"

if [[ ! -f .env ]]; then
  echo "local .env is required" >&2
  exit 1
fi

set -a
source .env
set +a

: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"

if [[ -d /opt/homebrew/opt/node@24/bin ]]; then
  export PATH="/opt/homebrew/opt/node@24/bin:$PATH"
fi

if nc -z 127.0.0.1 58000 >/dev/null 2>&1; then
  echo "127.0.0.1:58000 is already in use" >&2
  exit 1
fi

if nc -z 127.0.0.1 5173 >/dev/null 2>&1; then
  echo "127.0.0.1:5173 is already in use" >&2
  exit 1
fi

TEST_DB="dc_inventory_fullstack_$(date +%Y%m%d%H%M%S)_$$"
export TEST_DB
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dc-inventory-fullstack.XXXXXX")"
BACKEND_PID=""
FRONTEND_PID=""
DB_CREATED=0

cleanup() {
  status=$?
  trap - EXIT INT TERM
  set +e

  if [[ -n "$FRONTEND_PID" ]]; then
    kill "$FRONTEND_PID" >/dev/null 2>&1
    wait "$FRONTEND_PID" >/dev/null 2>&1
  fi

  if [[ -n "$BACKEND_PID" ]]; then
    kill "$BACKEND_PID" >/dev/null 2>&1
    wait "$BACKEND_PID" >/dev/null 2>&1
  fi

  if [[ "$DB_CREATED" = "1" ]]; then
    if docker compose -f compose.dev.yaml exec -T postgres \
      dropdb -U "$POSTGRES_USER" --force --if-exists "$TEST_DB" \
      </dev/null >/dev/null 2>&1; then
      echo "FULLSTACK_DATABASE_CLEANUP=PASS"
    else
      echo "FULLSTACK_DATABASE_CLEANUP=FAIL: $TEST_DB" >&2
      status=1
    fi
  fi

  if ! rm -rf "$TMP_DIR"; then
    echo "FULLSTACK_TEMP_CLEANUP=FAIL: $TMP_DIR" >&2
    status=1
  fi
  exit "$status"
}

trap cleanup EXIT INT TERM

wait_for_url() {
  name="$1"
  url="$2"
  log_file="$3"

  for _ in $(seq 1 60); do
    if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done

  echo "$name did not become ready" >&2
  cat "$log_file" >&2
  return 1
}

docker compose -f compose.dev.yaml up -d --no-recreate postgres >/dev/null

env -i PATH="$PATH" POSTGRES_DEV_PORT="${POSTGRES_DEV_PORT:-55432}" \
  python3 ops/tests/fullstack_db_guard.py topology


docker compose -f compose.dev.yaml exec -T postgres \
  createdb -U "$POSTGRES_USER" "$TEST_DB" </dev/null

DB_CREATED=1

export APP_ENV=test
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_DEV_PORT:-55432}/${TEST_DB}"
export REAL_INVENTORY_MUTATIONS_ENABLED=false
export EMAIL_DELIVERY_ENABLED=false

unset TELEGRAM_GATEWAY_URL
unset TELEGRAM_GATEWAY_SECRET
unset TELEGRAM_GATEWAY_TIMEOUT_SECONDS
unset MICROSOFT_GRAPH_TENANT_ID
unset MICROSOFT_GRAPH_CLIENT_ID
unset MICROSOFT_GRAPH_CLIENT_SECRET
unset MICROSOFT_GRAPH_SENDER

export TELEGRAM_BOT_TOKEN="123456789:local-fullstack-token"
export FULLSTACK_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
export FULLSTACK_TELEGRAM_USER_ID="42424242"
export ADMIN_TELEGRAM_USER_ID="$FULLSTACK_TELEGRAM_USER_ID"
export NOTIFICATION_TELEGRAM_USER_ID="42424243"
export TELEGRAM_WEBHOOK_SECRET="local-fullstack-webhook-secret"
export TELEGRAM_WEB_APP_URL="http://127.0.0.1:5173"

nonce="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

docker compose -f compose.dev.yaml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$TEST_DB" -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE cp15_fullstack_probe (token text NOT NULL);
      INSERT INTO cp15_fullstack_probe (token) VALUES ('$nonce');" \
  </dev/null >/dev/null

(
  cd backend
  env -i PATH="$PATH" APP_ENV=test DATABASE_URL="$DATABASE_URL" \
    TEST_DB="$TEST_DB" FULLSTACK_DB_NONCE="$nonce" \
    POSTGRES_DEV_PORT="${POSTGRES_DEV_PORT:-55432}" \
    REAL_INVENTORY_MUTATIONS_ENABLED=false \
    .venv/bin/python ../ops/tests/fullstack_db_guard.py verify
)

docker compose -f compose.dev.yaml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$TEST_DB" -v ON_ERROR_STOP=1 \
  -c 'DROP TABLE cp15_fullstack_probe' </dev/null >/dev/null

(
  cd backend
  env -i PATH="$PATH" APP_ENV=test DATABASE_URL="$DATABASE_URL" \
    REAL_INVENTORY_MUTATIONS_ENABLED=false .venv/bin/alembic upgrade head
)

# The override exists only in this runner's child processes, after fresh-DB
# creation, pre-migration identity verification, and migration.
export REAL_INVENTORY_MUTATIONS_ENABLED=true
export FULLSTACK_MUTATIONS_ENABLED=true

runtime_env=(
  "PATH=$PATH"
  "APP_ENV=test"
  "DATABASE_URL=$DATABASE_URL"
  "REAL_INVENTORY_MUTATIONS_ENABLED=true"
  "EMAIL_DELIVERY_ENABLED=false"
  "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN"
  "ADMIN_TELEGRAM_USER_ID=$ADMIN_TELEGRAM_USER_ID"
  "NOTIFICATION_TELEGRAM_USER_ID=$NOTIFICATION_TELEGRAM_USER_ID"
  "TELEGRAM_WEBHOOK_SECRET=$TELEGRAM_WEBHOOK_SECRET"
  "TELEGRAM_WEB_APP_URL=$TELEGRAM_WEB_APP_URL"
)

(
  cd backend
  exec env -i "${runtime_env[@]}" .venv/bin/uvicorn \
    app.main:app \
    --host 127.0.0.1 \
    --port 58000
) >"$TMP_DIR/backend.log" 2>&1 &

BACKEND_PID=$!

wait_for_url \
  "backend" \
  "http://127.0.0.1:58000/api/health/ready" \
  "$TMP_DIR/backend.log"

(
  cd frontend
  exec env -i PATH="$PATH" HOME="$HOME" ./node_modules/.bin/vite \
    --host 127.0.0.1 \
    --port 5173
) >"$TMP_DIR/frontend.log" 2>&1 &

FRONTEND_PID=$!

wait_for_url \
  "frontend" \
  "http://127.0.0.1:5173/" \
  "$TMP_DIR/frontend.log"

(
  cd frontend
  env -i PATH="$PATH" HOME="$HOME" \
    PLAYWRIGHT_BASE_URL="http://127.0.0.1:5173" \
    FULLSTACK_TELEGRAM_BOT_TOKEN="$FULLSTACK_TELEGRAM_BOT_TOKEN" \
    FULLSTACK_TELEGRAM_USER_ID="$FULLSTACK_TELEGRAM_USER_ID" \
    FULLSTACK_MUTATIONS_ENABLED=true \
    npm run test:e2e:fullstack
)

identity_state="$(
  docker compose -f compose.dev.yaml exec -T postgres \
    psql \
    -U "$POSTGRES_USER" \
    -d "$TEST_DB" \
    -At \
    -v ON_ERROR_STOP=1 \
    -c "
      SELECT u.role || '|' || u.access_status
      FROM telegram_identities ti
      JOIN users u ON u.id = ti.user_id
      WHERE ti.telegram_user_id = 42424242;
    " </dev/null
)"

test "$identity_state" = "OWNER|APPROVED"

session_count="$(
  docker compose -f compose.dev.yaml exec -T postgres \
    psql \
    -U "$POSTGRES_USER" \
    -d "$TEST_DB" \
    -At \
    -v ON_ERROR_STOP=1 \
    -c "
      SELECT count(*)
      FROM auth_sessions s
      JOIN telegram_identities ti
        ON ti.user_id = s.user_id
      WHERE ti.telegram_user_id = 42424242;
    " </dev/null
)"

test "$session_count" -ge 1

domain_state="$(docker compose -f compose.dev.yaml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$TEST_DB" -AtF '|' -v ON_ERROR_STOP=1 \
  -c "SELECT
    (SELECT count(*) FROM procurement_requests WHERE status = 'COMPLETED' AND final_movement_id IS NOT NULL),
    (SELECT count(*) FROM procurement_revisions),
    (SELECT count(*) FROM procurement_events),
    (SELECT count(*) FROM movements),
    (SELECT coalesce(sum(quantity), 0) FROM stock_balances),
    (SELECT coalesce(sum(quantity), 0) FROM user_item_custody_balances)
  " </dev/null)"
test "$domain_state" = "1|2|6|5|12|2"
echo "FULLSTACK_DATABASE_DOMAIN_STATE=PASS"

ACTUAL_ALEMBIC_HEAD="$(
  docker compose -f compose.dev.yaml exec -T postgres \
    psql \
    -U "$POSTGRES_USER" \
    -d "$TEST_DB" \
    -At \
    -v ON_ERROR_STOP=1 \
    -c "SELECT version_num FROM alembic_version" \
    </dev/null |
  tr -d '[:space:]'
)"

test "$ACTUAL_ALEMBIC_HEAD" = "$EXPECTED_ALEMBIC_HEAD"

echo "FULLSTACK_ALEMBIC_HEAD=$ACTUAL_ALEMBIC_HEAD"

drift="$(docker compose -f compose.dev.yaml exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$TEST_DB" -qAt -v ON_ERROR_STOP=1 \
  -f - <backend/scripts/reconcile_inventory_projections.sql)"
if [[ -n "$drift" ]]; then
  echo "FULLSTACK_PROJECTION_RECONCILIATION=FAIL" >&2
  exit 1
fi

echo "FULLSTACK_PROJECTION_RECONCILIATION=PASS"

echo "FULLSTACK_LOCAL_ISOLATION=PASS"
echo "FULLSTACK_LOCAL_DATABASE=$TEST_DB"
