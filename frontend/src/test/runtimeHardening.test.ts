import { describe, expect, it } from "vitest";

import dockerIgnore from "../../.dockerignore?raw";
import nginxConfig from "../../nginx.conf?raw";

function locationBody(signature: string): string {
  const marker = `${signature} {`;
  const start = nginxConfig.indexOf(marker);

  expect(start).toBeGreaterThanOrEqual(0);

  const bodyStart = nginxConfig.indexOf("\n", start) + 1;
  const end = nginxConfig.indexOf(
    "\n        }",
    bodyStart,
  );

  expect(bodyStart).toBeGreaterThan(start);
  expect(end).toBeGreaterThan(bodyStart);

  return nginxConfig.slice(bodyStart, end);
}

function expectSecurityHeaders(body: string): void {
  expect(body).toContain(
    "add_header X-Content-Type-Options nosniff always;",
  );
  expect(body).toContain(
    "add_header Referrer-Policy strict-origin-when-cross-origin always;",
  );
  expect(body).toContain(
    "add_header Content-Security-Policy \"default-src 'self'; base-uri 'self'; object-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'\" always;",
  );
  expect(body).toContain(
    'add_header Permissions-Policy "camera=(self), microphone=(), geolocation=(), payment=(), usb=()" always;',
  );
}

describe("production web hardening", () => {
  it("keeps CSP and Permissions-Policy on all explicit security-header scopes", () => {
    expect(
      nginxConfig.match(
        /add_header Content-Security-Policy/g,
      ),
    ).toHaveLength(3);

    expect(
      nginxConfig.match(
        /add_header Permissions-Policy/g,
      ),
    ).toHaveLength(3);
  });

  it("keeps security headers on immutable assets", () => {
    const body = locationBody("location /assets/");

    expectSecurityHeaders(body);
    expect(body).toContain(
      'add_header Cache-Control "public, immutable";',
    );
  });

  it("keeps security headers on index.html", () => {
    const body = locationBody(
      "location = /index.html",
    );

    expectSecurityHeaders(body);
    expect(body).toContain(
      'add_header Cache-Control "no-store";',
    );
  });

  it("excludes frontend environment files from Docker context", () => {
    const lines = dockerIgnore
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);

    expect(lines).toContain(".env*");
  });
});

describe("production API rate limiting", () => {
  it("defines independent general, sensitive, and Telegram webhook zones", () => {
    expect(nginxConfig).toContain(
      "limit_req_zone $api_rate_key zone=api_per_client:5m rate=30r/s;",
    );
    expect(nginxConfig).toContain(
      "limit_req_zone $sensitive_rate_key zone=sensitive_per_client:5m rate=10r/m;",
    );
    expect(nginxConfig).toContain(
      "limit_req_zone $telegram_webhook_rate_key zone=telegram_webhook:5m rate=50r/s;",
    );
    expect(nginxConfig).toContain(
      "limit_req_status 429;",
    );
  });

  it("limits sensitive POST routes by normalized client identity", () => {
    expect(nginxConfig).toContain(
      'map "$request_method:$uri" $sensitive_rate_key {',
    );
    expect(nginxConfig).toContain(
      "POST:/api/auth/telegram $client_ip;",
    );
    expect(nginxConfig).toContain(
      "POST:/api/access-requests $client_ip;",
    );
  });

  it("keeps Telegram webhook outside the general API bucket", () => {
    expect(nginxConfig).toContain(
      "/api/telegram/webhook \"\";",
    );
    expect(nginxConfig).toContain(
      "/api/telegram/webhook $client_ip;",
    );
  });

  it("applies all rate-limit zones before proxying API requests", () => {
    const body = locationBody("location /api/");

    expect(body).toContain(
      "limit_req zone=api_per_client burst=60 nodelay;",
    );
    expect(body).toContain(
      "limit_req zone=sensitive_per_client burst=5 nodelay;",
    );
    expect(body).toContain(
      "limit_req zone=telegram_webhook burst=100 nodelay;",
    );
  });
});
