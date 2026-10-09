// Deer Scout service worker.
// - App pages and data files: network first, fall back to the last saved copy (works without signal).
// - Map tiles are NOT cached here; offline maps need providers' terms checked first (Phase 4).
// - Weather requests always go to the network (forecasts go stale fast; the app caches them briefly itself).

const CACHE = "deer-scout-v1";
const SHELL = ["/", "/map/", "/saved/", "/settings/", "/property/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return; // tiles, weather, routing: straight to network

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(async () => {
        const hit = await caches.match(req, { ignoreSearch: url.pathname.startsWith("/property") });
        return hit || caches.match("/") || Response.error();
      }),
  );
});
