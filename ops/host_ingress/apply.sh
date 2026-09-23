#!/bin/sh
set -eu

CONFIRMATION="${1:-}"

if [ "$(id -u)" -ne 0 ]; then
    echo "must run as root" >&2
    exit 1
fi

if [ "$CONFIRMATION" != "--confirm=APPLY_HOST_DIRECT_INGRESS" ]; then
    echo "usage: $0 --confirm=APPLY_HOST_DIRECT_INGRESS" >&2
    exit 2
fi

ROOT="$(
    CDPATH= cd -- "$(dirname -- "$0")/../.." &&
    pwd
)"

SOURCE_ROOT="$ROOT/ops/host_ingress"

SITE_SOURCE="$SOURCE_ROOT/nginx/dc-inventory-direct.conf"
HOOK_SOURCE="$SOURCE_ROOT/certbot/reload-nginx"
VERIFY="$SOURCE_ROOT/verify.py"

SITE="/etc/nginx/sites-available/dc-inventory-direct"
ENABLED="/etc/nginx/sites-enabled/dc-inventory-direct"
HOOK="/etc/letsencrypt/renewal-hooks/deploy/reload-nginx"
RENEWAL="/etc/letsencrypt/renewal/app.spik-inventory.ru.conf"
ACME_ROOT="/var/www/letsencrypt"
INGRESS_DIR="/var/lib/dc-inventory-ingress"
INGRESS_SOCKET="$INGRESS_DIR/ingress.sock"
CERT="/etc/letsencrypt/live/app.spik-inventory.ru/fullchain.pem"
KEY="/etc/letsencrypt/live/app.spik-inventory.ru/privkey.pem"

for command in install ln readlink cp rm mktemp python3 systemctl; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "required command not found: $command" >&2
        exit 1
    }
done

test -x /usr/sbin/nginx
test -f "$SITE_SOURCE"
test -f "$HOOK_SOURCE"
test -f "$VERIFY"
test -f "$RENEWAL"
test -f "$CERT"
test -f "$KEY"
test -d "$INGRESS_DIR"
test -S "$INGRESS_SOCKET"
test -d /etc/nginx/sites-available
test -d /etc/nginx/sites-enabled
test -d /etc/letsencrypt/renewal-hooks/deploy

if [ -e "$ENABLED" ] && [ ! -L "$ENABLED" ]; then
    echo "refusing to replace non-symlink: $ENABLED" >&2
    exit 1
fi

BACKUP="$(
    mktemp -d \
        /var/tmp/dc-inventory-host-ingress.XXXXXX
)"

HAD_SITE=0
HAD_HOOK=0
HAD_ENABLED=0
OLD_ENABLED_TARGET=""

cleanup() {
    rm -rf "$BACKUP"
}

trap cleanup EXIT HUP INT TERM

if [ -e "$SITE" ]; then
    cp -a "$SITE" "$BACKUP/site"
    HAD_SITE=1
fi

if [ -e "$HOOK" ]; then
    cp -a "$HOOK" "$BACKUP/hook"
    HAD_HOOK=1
fi

if [ -L "$ENABLED" ]; then
    OLD_ENABLED_TARGET="$(readlink "$ENABLED")"
    HAD_ENABLED=1
fi

rollback() {
    echo "rolling back host ingress files" >&2

    if [ "$HAD_SITE" -eq 1 ]; then
        cp -a "$BACKUP/site" "$SITE"
    else
        rm -f "$SITE"
    fi

    if [ "$HAD_HOOK" -eq 1 ]; then
        cp -a "$BACKUP/hook" "$HOOK"
    else
        rm -f "$HOOK"
    fi

    if [ "$HAD_ENABLED" -eq 1 ]; then
        ln -sfn "$OLD_ENABLED_TARGET" "$ENABLED"
    else
        rm -f "$ENABLED"
    fi

    /usr/sbin/nginx -t >/dev/null 2>&1 &&
        systemctl reload nginx >/dev/null 2>&1 ||
        true
}

install \
    -d \
    -o root \
    -g root \
    -m 0755 \
    "$ACME_ROOT"

install \
    -o root \
    -g root \
    -m 0644 \
    "$SITE_SOURCE" \
    "$SITE"

install \
    -o root \
    -g root \
    -m 0755 \
    "$HOOK_SOURCE" \
    "$HOOK"

ln -sfn \
    "$SITE" \
    "$ENABLED"

if ! /usr/sbin/nginx -t; then
    rollback
    exit 1
fi

if ! systemctl reload nginx; then
    rollback
    exit 1
fi

if ! python3 "$VERIFY"; then
    rollback
    exit 1
fi

echo "HOST_DIRECT_INGRESS_APPLY=PASS"
