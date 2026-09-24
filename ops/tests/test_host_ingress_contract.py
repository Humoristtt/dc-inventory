#!/usr/bin/env python3

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

SITE = (
    ROOT
    / "ops"
    / "host_ingress"
    / "nginx"
    / "dc-inventory-direct.conf"
).read_text()

HOOK = (
    ROOT
    / "ops"
    / "host_ingress"
    / "certbot"
    / "reload-nginx"
).read_text()

APPLY = (
    ROOT
    / "ops"
    / "host_ingress"
    / "apply.sh"
).read_text()

VERIFY = (
    ROOT
    / "ops"
    / "host_ingress"
    / "verify.py"
).read_text()

CI = (
    ROOT
    / ".github"
    / "workflows"
    / "ci.yml"
).read_text()

assert SITE.count("server {") == 4

assert "server_tokens off;" in SITE

for fragment in (
    "listen 80 default_server;",
    "listen [::]:80 default_server;",
    "listen 443 ssl default_server;",
    "listen [::]:443 ssl default_server;",
    "ssl_reject_handshake on;",
    "return 444;",
):
    assert fragment in SITE

for fragment in (
    "listen 80;",
    "listen [::]:80;",
    "listen 443 ssl;",
    "listen [::]:443 ssl;",
):
    assert fragment in SITE

assert (
    SITE.count(
        "server_name "
        "app.spik-inventory.ru;"
    )
    == 2
)

assert (
    "location ^~ "
    "/.well-known/acme-challenge/"
    in SITE
)

assert (
    "root /var/www/letsencrypt;"
    in SITE
)

assert (
    "return 301 "
    "https://$host$request_uri;"
    in SITE
)

assert (
    "ssl_certificate "
    "/etc/letsencrypt/live/"
    "app.spik-inventory.ru/"
    "fullchain.pem;"
    in SITE
)

assert (
    "ssl_certificate_key "
    "/etc/letsencrypt/live/"
    "app.spik-inventory.ru/"
    "privkey.pem;"
    in SITE
)

assert (
    "ssl_protocols "
    "TLSv1.2 TLSv1.3;"
    in SITE
)

assert (
    "proxy_pass "
    "http://unix:"
    "/var/lib/"
    "dc-inventory-ingress/"
    "ingress.sock;"
    in SITE
)

for fragment in (
    (
        "proxy_set_header "
        "Host $host;"
    ),
    (
        "proxy_set_header "
        "X-Real-IP $remote_addr;"
    ),
    (
        "proxy_set_header "
        "X-Forwarded-For "
        "$proxy_add_x_forwarded_for;"
    ),
    (
        "proxy_set_header "
        "X-Forwarded-Proto $scheme;"
    ),
    (
        "proxy_set_header "
        "Upgrade $http_upgrade;"
    ),
    (
        "proxy_set_header "
        "Connection "
        "$connection_upgrade;"
    ),
):
    assert fragment in SITE

assert "CF-Connecting-IP" not in SITE
assert "cloudflared" not in SITE.lower()
assert "localhost:8080" not in SITE
assert "127.0.0.1:8080" not in SITE

assert HOOK == (
    "#!/bin/sh\n"
    "set -eu\n"
    "\n"
    "/usr/sbin/nginx -t\n"
    "/bin/systemctl reload nginx\n"
)

assert (
    "--confirm="
    "APPLY_HOST_DIRECT_INGRESS"
    in APPLY
)

assert (
    "install \\\n"
    "    -o root \\\n"
    "    -g root \\\n"
    "    -m 0644"
    in APPLY
)

assert (
    "install \\\n"
    "    -o root \\\n"
    "    -g root \\\n"
    "    -m 0755"
    in APPLY
)

assert "/usr/sbin/nginx -t" in APPLY
assert "systemctl reload nginx" in APPLY
assert "rollback" in APPLY
assert (
    'test -S "$INGRESS_SOCKET"'
    in APPLY
)

for fragment in (
    (
        "require_exact_file(\n"
        "        SITE_SOURCE,\n"
        "        SITE,\n"
        "        0o644,"
    ),
    (
        "require_exact_file(\n"
        "        HOOK_SOURCE,\n"
        "        HOOK,\n"
        "        0o755,"
    ),
    'require_service("nginx")',
    'require_service("certbot.timer")',
    "if port_bindings:",
    "HOST_DIRECT_INGRESS=PASS",
):
    assert fragment in VERIFY, fragment

assert re.search(
    (
        r"- name: Host direct-ingress contract\n"
        r"\s+shell: bash\n"
        r"\s+run: \|\n"
        r"\s+python3 -B "
        r"ops/tests/"
        r"test_host_ingress_contract.py\n"
        r"\s+python3 -m py_compile "
        r"ops/host_ingress/verify.py\n"
        r"\s+sh -n "
        r"ops/host_ingress/apply.sh\n"
        r"\s+sh -n "
        r"ops/host_ingress/"
        r"certbot/reload-nginx"
    ),
    CI,
)

print(
    "HOST_DIRECT_INGRESS_CONTRACT=PASS"
)
