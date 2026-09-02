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
}

describe("production web hardening", () => {
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
