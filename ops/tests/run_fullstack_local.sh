set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$ROOT"

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
    docker compose -f compose.dev.yaml exec -T postgres \
      dropdb -U "$POSTGRES_USER" --force --if-exists "$TEST_DB" \
      >/dev/null 2>&1
  fi

  rm -rf "$TMP_DIR"
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

docker compose -f compose.dev.yaml up -d postgres >/dev/null

docker compose -f compose.dev.yaml exec -T postgres \
  createdb -U "$POSTGRES_USER" "$TEST_DB"

DB_CREATED=1

export APP_ENV=test
export DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_DEV_PORT:-55432}/${TEST_DB}"
export REAL_INVENTORY_MUTATIONS_ENABLED=false

unset TELEGRAM_GATEWAY_URL
unset TELEGRAM_GATEWAY_SECRET
unset TELEGRAM_GATEWAY_TIMEOUT_SECONDS

export TELEGRAM_BOT_TOKEN="123456789:local-fullstack-token"
export FULLSTACK_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
export FULLSTACK_TELEGRAM_USER_ID="42424242"
export ADMIN_TELEGRAM_USER_ID="$FULLSTACK_TELEGRAM_USER_ID"
export NOTIFICATION_TELEGRAM_USER_ID="42424243"
export TELEGRAM_WEBHOOK_SECRET="local-fullstack-webhook-secret"
export TELEGRAM_WEB_APP_URL="http://127.0.0.1:5173"

(
  cd backend
  .venv/bin/alembic upgrade head
)

(
  cd backend
  exec .venv/bin/uvicorn \
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
  exec ./node_modules/.bin/vite \
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
  PLAYWRIGHT_BASE_URL="http://127.0.0.1:5173" \
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
    "
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
    "
)"

test "$session_count" -ge 1

echo "FULLSTACK_LOCAL_ISOLATION=PASS"
echo "FULLSTACK_LOCAL_DATABASE=$TEST_DB"
