// After `next build`: list every file of the static site so the service worker can save the whole
// app on the phone at install (out/precache.json), and stamp a build version into out/sw.js so
// phones pick up a new version when the app or its data change.
import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

// fileURLToPath (not .pathname) so folder names with spaces work.
const OUT = fileURLToPath(new URL("../out/", import.meta.url));
const SKIP = new Set(["sw.js", "precache.json"]);
// MapLibre 6 builds a few file addresses at runtime, so Next.js copies every .mjs file in its dist
// folder into _next/static/media. The app only ever loads the worker (setWorkerUrl in MapView.tsx);
// the development builds, the empty "shared" placeholders and a second copy of the main file are
// never requested, so phones don't need to download them (about 5 MB).
const UNUSED = /^_next\/static\/media\/maplibre-gl(-dev|-worker-dev|-shared|-shared-dev)?\.[^/]+\.mjs$/;

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const hash = createHash("sha256");
const files = [];
for (const p of walk(OUT).sort()) {
  const rel = relative(OUT, p).split(sep).join("/");
  if (SKIP.has(rel)) continue;
  hash.update(rel);
  hash.update(readFileSync(p));
  if (UNUSED.test(rel)) continue; // still counted in the version stamp, just not downloaded
  if (rel === "index.html") files.push("/");
  else if (rel.endsWith("/index.html")) files.push("/" + rel.slice(0, -"index.html".length));
  else files.push("/" + rel);
}
const version = hash.digest("hex").slice(0, 12);
writeFileSync(join(OUT, "precache.json"), JSON.stringify({ version, files }));
const swPath = join(OUT, "sw.js");
writeFileSync(swPath, readFileSync(swPath, "utf8").replace("__BUILD_VERSION__", version));
const mb = files.reduce((s, f) => s + statSync(join(OUT, f.endsWith("/") ? f + "index.html" : f)).size, 0) / 1048576;
console.log(`precache: ${files.length} files, ${mb.toFixed(1)} MB, version ${version}`);
