import {
  readFileSync,
  readdirSync,
  statSync,
} from "node:fs";

import {
  join,
  relative,
  resolve,
} from "node:path";

const root = resolve(
  import.meta.dirname,
  "..",
);

const src = join(root, "src");

function filesUnder(directory) {
  const result = [];

  for (const name of readdirSync(directory)) {
    const path = join(directory, name);
    const stat = statSync(path);

    if (stat.isDirectory()) {
      result.push(...filesUnder(path));
      continue;
    }

    result.push(path);
  }

  return result;
}

const files = filesUnder(src);
const violations = [];

const legacyHeaderTokens = [
  "catalog-landing-header",
  "category-header",
  "detail-header",
  "warehouse-page-header",
  "more-page__header",
  "admin-users-page__header",
  "page-toolbar",
];

for (const path of files) {
  if (
    !path.endsWith(".css")
    && !path.endsWith(".tsx")
    && !path.endsWith(".ts")
  ) {
    continue;
  }

  const content = readFileSync(
    path,
    "utf8",
  );

  for (const token of legacyHeaderTokens) {
    if (content.includes(token)) {
      violations.push(
        `${relative(root, path)}: legacy header token ${token}`,
      );
    }
  }
}

const canonicalCss = resolve(
  src,
  "shared/ui/design-system.css",
);

for (const path of files) {
  if (!path.endsWith(".css")) {
    continue;
  }

  if (resolve(path) === canonicalCss) {
    continue;
  }

  const content = readFileSync(
    path,
    "utf8",
  );

  for (const selector of [
    ".compact-brand",
    ".telegram-fullscreen-button",
  ]) {
    if (content.includes(selector)) {
      violations.push(
        `${relative(root, path)}: shared selector ${selector} outside shared/ui`,
      );
    }
  }
}

const pageFiles = files.filter(
  (path) =>
    path.includes(`${join("src", "pages")}/`)
    && path.endsWith(".tsx"),
);

for (const path of pageFiles) {
  const content = readFileSync(
    path,
    "utf8",
  );

  for (const primitive of [
    "SpikatelBrand",
    "TelegramFullscreenButton",
  ]) {
    if (content.includes(primitive)) {
      violations.push(
        `${relative(root, path)}: page directly owns ${primitive}`,
      );
    }
  }
}

const main = readFileSync(
  join(src, "main.tsx"),
  "utf8",
);

if (
  !main.includes(
    'import "./shared/ui/design-system.css";',
  )
) {
  violations.push(
    "src/main.tsx: shared design-system stylesheet is not loaded",
  );
}

if (violations.length > 0) {
  console.error(
    "Design-system architecture violations:",
  );

  for (const violation of violations) {
    console.error(`- ${violation}`);
  }

  process.exit(1);
}

console.log(
  "DESIGN_SYSTEM_ARCHITECTURE=PASS",
);
