import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";

const dist = new URL("../dist/", import.meta.url);
const manifest = JSON.parse(await readFile(new URL(".vite/manifest.json", dist), "utf8"));
const initial = new Set();
function visit(key) {
  if (initial.has(key)) return;
  initial.add(key);
  for (const dependency of manifest[key].imports ?? []) visit(dependency);
}
for (const [key, chunk] of Object.entries(manifest)) {
  if (chunk.isEntry) visit(key);
}
let bytes = 0;
let gzip = 0;
for (const key of initial) {
  const file = manifest[key].file;
  if (!file.endsWith(".js")) continue;
  const content = await readFile(new URL(file, dist));
  bytes += content.length;
  gzip += gzipSync(content).length;
}
// Includes recursively imported shared chunks, not just the entry filename.
assert(bytes <= 310_000, `Initial JS ${bytes} exceeds 310000 bytes`);
assert(gzip <= 100_000, `Initial gzip JS ${gzip} exceeds 100000 bytes`);
for (const route of [
  "catalog/CatalogLandingPage", "catalog/CategoryPage", "catalog/ItemDetailPage",
  "catalog/ItemFormPage", "inventory/MovementsPage", "inventory/LocationsPage",
]) {
  const key = `src/pages/${route}.tsx`;
  assert(manifest[key]?.isDynamicEntry, `${route} must remain a lazy route`);
  assert(!initial.has(key), `${route} must not enter the startup import graph`);
}
console.log(`Bundle contract passed: initial JS ${bytes} bytes; gzip ${gzip} bytes; ${initial.size} initial chunks.`);
