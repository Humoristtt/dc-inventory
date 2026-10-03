import {
  readFileSync,
} from "node:fs";

import {
  resolve,
} from "node:path";

const root = resolve(
  import.meta.dirname,
  "..",
);

const tokens = readFileSync(
  resolve(
    root,
    "src/app/styles/tokens.css",
  ),
  "utf8",
);

const requiredTokens = [
  ["--color-brand-cream", "#ffecb7"],
  ["--color-brand-neon", "#fcff2e"],
  ["--color-brand-primary", "#feaa13"],
  ["--color-brand-orange-hot", "#ff6600"],
  ["--color-brand-red", "#ff0000"],
  ["--color-brand-soft", "#f9eb6e"],
  ["--color-brand-wine", "#a1021b"],
  ["--color-brand-black", "#000000"],
  ["--color-brand-deep", "#d69303"],
  ["--font-weight-regular", "400"],
  ["--font-weight-medium", "500"],
  ["--font-weight-bold", "700"],
];

const violations = [];

for (const [token, expected] of requiredTokens) {
  const marker = `${token}: ${expected};`;

  if (!tokens.includes(marker)) {
    violations.push(
      `${token} must match Spikatel guidebook value ${expected}`,
    );
  }
}

for (const font of [
  '"Inter Variable"',
  '"Inter"',
]) {
  if (!tokens.includes(font)) {
    violations.push(
      `brand font stack must include ${font}`,
    );
  }
}

if (violations.length > 0) {
  console.error("Brand guidebook violations:");

  for (const violation of violations) {
    console.error(`- ${violation}`);
  }

  process.exit(1);
}

console.log("BRAND_GUIDEBOOK_CONTRACT=PASS");
