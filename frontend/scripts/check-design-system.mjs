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

const root = resolve(import.meta.dirname, "..");
const src = join(root, "src");

function filesUnder(directory) {
  const result = [];

  for (const name of readdirSync(directory)) {
    const path = join(directory, name);
    const stat = statSync(path);

    if (stat.isDirectory()) {
      result.push(...filesUnder(path));
    } else {
      result.push(path);
    }
  }

  return result;
}

const files = filesUnder(src);
const violations = [];
const canonicalCss = resolve(
  src,
  "shared/ui/design-system.css",
);
const controlsSource = resolve(
  src,
  "shared/ui/controls.tsx",
);

function addViolation(path, message) {
  violations.push(
    `${relative(root, path)}: ${message}`,
  );
}

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

  const content = readFileSync(path, "utf8");

  for (const token of legacyHeaderTokens) {
    if (content.includes(token)) {
      addViolation(
        path,
        `legacy header token ${token}`,
      );
    }
  }
}

for (const path of files) {
  if (
    !path.endsWith(".tsx")
    || path.endsWith(".test.tsx")
    || path.includes(`${join("src", "test")}/`)
    || resolve(path) === controlsSource
  ) {
    continue;
  }

  const content = readFileSync(path, "utf8");

  for (const rawTag of [
    "<button",
    "<input",
    "<select",
    "<textarea",
  ]) {
    if (content.includes(rawTag)) {
      addViolation(
        path,
        `raw ${rawTag.slice(1)} must use shared/ui controls`,
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
  ".ds-control {",
]) {
  if (globalStyles.includes(selector)) {
    violations.push(
      `src/app/styles/global.css: shared UI selector ${selector} outside shared/ui`,
    );
  }
}

for (const path of files) {
  if (
    !path.endsWith(".css")
    || resolve(path) === canonicalCss
  ) {
    continue;
  }

  const content = readFileSync(path, "utf8");

  for (const selector of [
    ".compact-brand",
    ".telegram-fullscreen-button",
    ".ds-control",
    ".ds-input",
    ".ds-select",
    ".ds-textarea",
  ]) {
    if (content.includes(selector)) {
      addViolation(
        path,
        `shared selector ${selector} outside shared/ui`,
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
  "pages/procurement/ProcurementCreatePage.tsx",
  "pages/procurement/ProcurementDetailPage.tsx",
];

for (const relativePath of requiredFormSurfaces) {
  const path = join(src, relativePath);
  const content = readFileSync(path, "utf8");

  if (!content.includes("form-surface")) {
    addViolation(
      path,
      "canonical form-surface contract missing",
    );
  }
}

const searchFieldPath = join(
  src,
  "features/catalog/SearchField.tsx",
);
const searchField = readFileSync(
  searchFieldPath,
  "utf8",
);

if (!searchField.includes('appearance="bare"')) {
  addViolation(
    searchFieldPath,
    "search input must explicitly use the bare shared-control variant",
  );
}

const geometryProperties = [
  "height:",
  "min-height:",
  "padding:",
  "padding-inline:",
  "padding-block:",
  "border:",
  "border-radius:",
  "font-size:",
  "font-weight:",
];

const rulePattern = /([^{}]+)\{([^{}]*)\}/g;

for (const path of files) {
  if (
    !path.endsWith(".css")
    || resolve(path) === canonicalCss
  ) {
    continue;
  }

  const content = readFileSync(path, "utf8");
  let match;

  while ((match = rulePattern.exec(content)) !== null) {
    const selector = match[1].trim();
    const body = match[2];

    const mentionsFormControl =
      /\binput\b|\bselect\b|\btextarea\b/.test(
        selector,
      );

    if (mentionsFormControl) {
      const allowedChoiceControl =
        selector.includes(".filter-option input")
        || selector.includes(".catalog-switch input")
        || selector.includes('input[type="checkbox"]')
        || selector.includes('input[type="radio"]');

      const allowedBareSearch =
        selector.includes(".search-field input");

      const allowedPseudoOnly =
        selector.includes("::-webkit-")
        || selector.includes("::placeholder")
        || selector.includes(":focus");

      if (
        !allowedChoiceControl
        && !allowedBareSearch
        && !allowedPseudoOnly
      ) {
        for (const property of geometryProperties) {
          if (body.includes(property)) {
            addViolation(
              path,
              `control geometry ${property} in ${selector}; use shared/ui`,
            );
          }
        }
      }
    }

    if (
      /\.button\b|\.ds-button\b/.test(selector)
    ) {
      for (const property of geometryProperties) {
        if (body.includes(property)) {
          addViolation(
            path,
            `button geometry ${property} in ${selector}; use shared/ui`,
          );
        }
      }
    }
  }
}

const pageFiles = files.filter(
  (path) =>
    path.includes(`${join("src", "pages")}/`)
    && path.endsWith(".tsx"),
);

for (const path of pageFiles) {
  const content = readFileSync(path, "utf8");

  for (const primitive of [
    "SpikatelBrand",
    "TelegramFullscreenButton",
  ]) {
    if (content.includes(primitive)) {
      addViolation(
        path,
        `page directly owns ${primitive}`,
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
