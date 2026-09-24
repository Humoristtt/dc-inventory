import { describe, expect, it } from "vitest";

import appSource from "../app/App.tsx?raw";
import routeModulesSource from "../app/routeModules.ts?raw";
import mainSource from "../main.tsx?raw";

import dockerIgnore from "../../.dockerignore?raw";
import indexSource from "../../index.html?raw";
import nginxConfig from "../../nginx.conf?raw";
import nginxServerInclude from "../../nginx-server.inc?raw";
import dockerfileSource from "../../Dockerfile?raw";

function locationBody(signature: string): string {
  const marker = `${signature} {`;
  const start = nginxServerInclude.indexOf(marker);

  expect(start).toBeGreaterThanOrEqual(0);

  const bodyStart = nginxServerInclude.indexOf("\n", start) + 1;
  const end = nginxServerInclude.indexOf(
    "\n        }",
    bodyStart,
  );

  expect(bodyStart).toBeGreaterThan(start);
  expect(end).toBeGreaterThan(bodyStart);

  return nginxServerInclude.slice(bodyStart, end);
}

function expectSecurityHeaders(body: string): void {
  expect(body).toContain(
    'add_header Strict-Transport-Security "max-age=31536000" always;',
  );
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

describe("frontend source hygiene", () => {
  it("does not load the retired DOM mutation hotfix", () => {
    expect(indexSource).not.toContain(
      "search-input-assistance-20260922",
    );
  });
});

describe("production web hardening", () => {
  it("ships the shared Nginx configuration to both server entrypoints", () => {
    expect(dockerfileSource).toContain(
      "COPY nginx-server.inc /etc/nginx/server-common.inc",
    );
    expect(
      nginxConfig.match(/include \/etc\/nginx\/server-common\.inc;/g),
    ).toHaveLength(2);
  });

  it("keeps HSTS on all explicit security-header scopes", () => {
    expect(
      nginxServerInclude.match(
        /add_header Strict-Transport-Security/g,
      ),
    ).toHaveLength(3);
  });

  it("keeps CSP and Permissions-Policy on all explicit security-header scopes", () => {
    expect(
      nginxServerInclude.match(
        /add_header Content-Security-Policy/g,
      ),
    ).toHaveLength(3);

    expect(
      nginxServerInclude.match(
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
  it("trusts only the host-normalized client IP on the Unix socket", () => {
    expect(nginxConfig).toContain("set_real_ip_from unix:;");
    expect(nginxConfig).toContain(
      "real_ip_header X-Real-IP;",
    );
    expect(nginxConfig).not.toContain(
      "real_ip_header CF-Connecting-IP;",
    );
    expect(nginxServerInclude).toContain(
      "proxy_set_header X-Real-IP $remote_addr;",
    );
    expect(nginxServerInclude).toContain(
      "proxy_set_header X-Forwarded-For $remote_addr;",
    );
  });

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
      "POST:/api/auth/telegram $remote_addr;",
    );
    expect(nginxConfig).toContain(
      "POST:/api/access-requests $remote_addr;",
    );
  });

  it("keeps Telegram webhook outside the general API bucket", () => {
    expect(nginxConfig).toContain(
      "/api/telegram/webhook \"\";",
    );
    expect(nginxConfig).toContain(
      "/api/telegram/webhook $remote_addr;",
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

describe("CP-07 route loading contract", () => {
  it("preloads the requested route without warming every page", () => {
    expect(mainSource).toContain(
      "void preloadRouteForPath(window.location.pathname);",
    );

    expect(appSource).not.toContain("preloadApplicationRoutes");

    expect(routeModulesSource).not.toContain(
      "export async function preloadApplicationRoutes",
    );
  });
});
