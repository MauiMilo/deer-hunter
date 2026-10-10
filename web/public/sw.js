// Deer Scout service worker: makes the app work with weak or no signal.
//
// - App files and data: the whole app is saved on install (list in /precache.json, written at
//   build time). Afterwards each request tries the network for up to 4 seconds and falls back to
//   the saved copy; a late network answer still refreshes the saved copy for next time.
// - Map tiles (USGS topo, satellite, 3DEP LiDAR relief) and the label font: served from the
//   phone first. Areas you save for offline live in SAVED; tiles you've simply looked at are kept
//   in RECENT (capped). USGS map services are public domain.
// - Weather is never cached here (the app keeps the last forecast itself and labels its age).

const VERSION = "__BUILD_VERSION__";
const APP = `deer-scout-app-${VERSION}`;
const SAVED = "deer-scout-tiles-saved";
const RECENT = "deer-scout-tiles-recent";
const RECENT_MAX = 3000;
const NET_WAIT_MS = 4000;

const HILLSHADE_BASE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage";
const TILE_HOSTS = ["basemap.nationalmap.gov", "elevation.nationalmap.gov", "demotiles.maplibre.org"];

// Same rule as tileKey() in src/lib/offline.ts.
function tileKey(url) {
  if (!url.startsWith(HILLSHADE_BASE)) return url;
  try {
    const u = new URL(url);
    const b = u.searchParams.get("bbox");
    if (!b) return url;
    const r = b.split(",").map((v) => (Math.round(Number(v) * 10) / 10).toFixed(1));
    return `${HILLSHADE_BASE}?bbox=${r.join(",")}&hillshade=1`;
  } catch {
    return url;
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(APP);
      let files = ["/", "/map/", "/saved/", "/settings/", "/property/"];
      try {
        const res = await fetch("/precache.json", { cache: "no-store" });
        if (res.ok) files = (await res.json()).files;
      } catch {
        /* offline during install: keep the basic list */
      }
      // One by one, so a single missing file doesn't stop the rest.
      for (let i = 0; i < files.length; i += 8) {
        await Promise.allSettled(files.slice(i, i + 8).map((f) => cache.add(new Request(f, { cache: "reload" }))));
      }
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith("deer-scout-app-") && k !== APP).map((k) => caches.delete(k))))
      .then(() => caches.delete("deer-scout-v1"))
      .then(() => self.clients.claim()),
  );
});

let puts = 0;
async function trimRecent(cache) {
  const keys = await cache.keys();
  const extra = keys.length - RECENT_MAX;
  for (let i = 0; i < extra; i++) await cache.delete(keys[i]);
}

async function tile(req) {
  const key = tileKey(req.url);
  if (req.cache === "no-store") {
    // Saving an area for offline: the page stores it itself.
    try {
      return await fetch(req);
    } catch {
      return new Response("", { status: 504, statusText: "Offline" });
    }
  }
  const saved = await (await caches.open(SAVED)).match(key);
  if (saved) return saved;
  const recent = await caches.open(RECENT);
  const hit = await recent.match(key);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res.ok && res.type !== "opaque") {
      await recent.put(key, res.clone());
      if (++puts % 100 === 0) trimRecent(recent);
    }
    return res;
  } catch {
    return new Response("", { status: 504, statusText: "Offline and not saved" });
  }
}

async function appFile(event, req, url) {
  const cache = await caches.open(APP);
  const network = fetch(req).then((res) => {
    if (res.ok) cache.put(req, res.clone());
    return res;
  });
  event.waitUntil(network.then(() => undefined, () => undefined));
  const timeout = new Promise((resolve) => setTimeout(() => resolve(null), NET_WAIT_MS));
  const first = await Promise.race([network.catch(() => null), timeout]);
  if (first) return first;
  const nav = req.mode === "navigate";
  const saved = (await cache.match(req, { ignoreSearch: nav || url.pathname.startsWith("/property") })) || (nav ? await cache.match("/") : null);
  if (saved) return saved;
  try {
    return await network;
  } catch {
    return Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (TILE_HOSTS.includes(url.hostname)) {
    event.respondWith(tile(req));
    return;
  }
  if (url.origin !== self.location.origin) return; // weather and anything else: straight to the network
  event.respondWith(appFile(event, req, url));
});
