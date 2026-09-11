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

const tokenStyles = readFileSync(
  join(src, "app/styles/tokens.css"),
  "utf8",
);

if (tokenStyles.includes("--radius-control")) {
  violations.push(
    "src/app/styles/tokens.css: duplicate --radius-control semantic token",
  );
}

const globalStyles = readFileSync(
  join(src, "app/styles/global.css"),
  "utf8",
);

for (const selector of [
  ".button {",
  ".icon-button {",
  ".section-kicker {",
]) {
  if (globalStyles.includes(selector)) {
    violations.push(
      `src/app/styles/global.css: shared UI selector ${selector} outside shared/ui`,
    );
  }
}

const forbiddenFeatureControlTokens = [
  ".catalog-form__field input",
  ".admin-users__filters input",
  ".admin-users__button",
  ".warehouse-form input",
  ".location-editor__form input",
];

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

  for (
    const token
    of forbiddenFeatureControlTokens
  ) {
    if (content.includes(token)) {
      violations.push(
        `${relative(root, path)}: base control geometry ${token} outside shared/ui`,
      );
    }
  }
}

const requiredFormSurfaces = [
  "pages/catalog/ItemFormPage.tsx",
  "pages/admin/AdminUsersPage.tsx",
  "pages/inventory/LocationsPage.tsx",
  "pages/inventory/MovementsPage.tsx",
  "features/inventory/ItemInventoryPanel.tsx",
];

for (const relativePath of requiredFormSurfaces) {
  const content = readFileSync(
    join(src, relativePath),
    "utf8",
  );

  if (!content.includes("form-surface")) {
    violations.push(
      `src/${relativePath}: canonical form-surface contract missing`,
    );
  }
}

function selectorBlocks(
  content,
  selector,
) {
  const marker = `${selector} {`;
  const blocks = [];
  let cursor = 0;

  while (true) {
    const start =
      content.indexOf(
        marker,
        cursor,
      );

    if (start === -1) {
      break;
    }

    const end =
      content.indexOf(
        "}",
        start,
      );

    if (end === -1) {
      break;
    }

    blocks.push(
      content.slice(
        start,
        end + 1,
      ),
    );

    cursor = end + 1;
  }

  return blocks;
}

for (
  const [
    relativePath,
    selector,
  ] of [
    [
      "features/admin/access-admin.css",
      ".more-card span",
    ],
    [
      "features/catalog/catalog.css",
      ".category-tile p",
    ],
  ]
) {
  const content = readFileSync(
    join(
      src,
      relativePath,
    ),
    "utf8",
  );

  const blocks =
    selectorBlocks(
      content,
      selector,
    );

  if (blocks.length === 0) {
    violations.push(
      `src/${relativePath}: secondary typography selector ${selector} missing`,
    );
    continue;
  }

  if (
    !blocks.some(
      (block) =>
        block.includes(
          "font-size: var(--font-meta);",
        ),
    )
  ) {
    violations.push(
      `src/${relativePath}: ${selector} must use --font-meta`,
    );
  }

  for (const block of blocks) {
    if (
      block.includes("font-size:")
      && !block.includes(
        "font-size: var(--font-meta);",
      )
    ) {
      violations.push(
        `src/${relativePath}: ${selector} overrides shared secondary typography`,
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
