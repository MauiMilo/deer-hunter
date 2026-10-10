// Offline maps: save the map tiles for an area onto the phone so the map works with no signal.
//
// Tiles are stored with the browser's Cache Storage under SAVED_CACHE; the service worker
// (public/sw.js) serves them before trying the network. The same key rule lives in sw.js.

import { GLYPHS, HILLSHADE_BASE, HILLSHADE_MINZOOM, HILLSHADE_TILES, IMAGERY_TILES, LABEL_FONT, MAXZOOM, TOPO_TILES } from "./mapsources";
import { loadList, save } from "./storage";

export const SAVED_CACHE = "deer-scout-tiles-saved";
export const AREAS_KEY = "ds.offline.areas";
export const MAX_TILES = 4000;
const AVG_KB = { topo: 25, imagery: 30, hillshade: 45 };

export type BBox = [number, number, number, number]; // west, south, east, north

export interface SavedArea {
  id: string;
  name: string;
  bbox: BBox;
  minZoom: number;
  tiles: number;
  failed: number;
  bytes: number;
  savedAt: number;
}

const HALF = Math.PI * 6378137; // half the width of the web mercator world, meters

export function lonLatToTile(lon: number, lat: number, z: number): { x: number; y: number } {
  const n = 2 ** z;
  const x = Math.floor(((lon + 180) / 360) * n);
  const r = (lat * Math.PI) / 180;
  const y = Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n);
  return { x: Math.min(n - 1, Math.max(0, x)), y: Math.min(n - 1, Math.max(0, y)) };
}

export function tilesIn(bbox: BBox, z: number): { x: number; y: number }[] {
  const a = lonLatToTile(bbox[0], bbox[3], z);
  const b = lonLatToTile(bbox[2], bbox[1], z);
  const out = [];
  for (let x = a.x; x <= b.x; x++) for (let y = a.y; y <= b.y; y++) out.push({ x, y });
  return out;
}

export function tileBBox3857(x: number, y: number, z: number): [number, number, number, number] {
  const size = (2 * HALF) / 2 ** z;
  const minx = -HALF + x * size;
  const maxy = HALF - y * size;
  return [minx, maxy - size, minx + size, maxy];
}

/** Cache key for a tile request. Hillshade tiles are keyed by their box rounded to 0.1 m, so a tile the
 * map asks for and the same tile saved here match even if the numbers print slightly differently. */
export function tileKey(url: string): string {
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

function xyz(tpl: string, x: number, y: number, z: number) {
  return tpl.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
}

export function areaUrls(bbox: BBox, minZoom = 10): string[] {
  const urls: string[] = [];
  for (let z = minZoom; z <= MAXZOOM.topo; z++) for (const t of tilesIn(bbox, z)) urls.push(xyz(TOPO_TILES, t.x, t.y, z));
  for (let z = minZoom; z <= MAXZOOM.imagery; z++) for (const t of tilesIn(bbox, z)) urls.push(xyz(IMAGERY_TILES, t.x, t.y, z));
  for (let z = Math.max(minZoom, HILLSHADE_MINZOOM); z <= MAXZOOM.hillshade; z++)
    for (const t of tilesIn(bbox, z)) urls.push(HILLSHADE_TILES.replace("{bbox-epsg-3857}", tileBBox3857(t.x, t.y, z).join(",")));
  urls.push(GLYPHS.replace("{fontstack}", LABEL_FONT).replace("{range}", "0-255"));
  return urls;
}

export function estimate(bbox: BBox, minZoom = 10): { tiles: number; mb: number } {
  let kb = 0;
  let tiles = 0;
  for (let z = minZoom; z <= 17; z++) {
    const n = tilesIn(bbox, z).length;
    if (z <= MAXZOOM.topo) {
      tiles += 2 * n;
      kb += n * (AVG_KB.topo + AVG_KB.imagery);
    }
    if (z >= HILLSHADE_MINZOOM && z <= MAXZOOM.hillshade) {
      tiles += n;
      kb += n * AVG_KB.hillshade;
    }
  }
  return { tiles, mb: Math.round(kb / 102.4) / 10 };
}

/** Pad a box by `m` meters on every side. */
export function padBBox(b: BBox, m: number): BBox {
  const dLat = m / 111320;
  const dLon = m / (111320 * Math.cos((((b[1] + b[3]) / 2) * Math.PI) / 180));
  return [b[0] - dLon, b[1] - dLat, b[2] + dLon, b[3] + dLat];
}

export function listAreas(): SavedArea[] {
  return loadList<SavedArea>(AREAS_KEY);
}

export function offlineSupported(): boolean {
  return typeof caches !== "undefined" && typeof fetch !== "undefined";
}

export async function saveArea(
  name: string,
  bbox: BBox,
  opts: { minZoom?: number; onProgress?: (done: number, total: number) => void; signal?: AbortSignal } = {},
): Promise<SavedArea> {
  const urls = areaUrls(bbox, opts.minZoom ?? 10);
  if (urls.length > MAX_TILES) throw new Error(`That area needs ${urls.length.toLocaleString()} map tiles; zoom in to a smaller area (limit ${MAX_TILES.toLocaleString()}).`);
  try {
    await navigator.storage?.persist?.();
  } catch {
    /* the browser may say no; tiles are still saved, just not protected from cleanup */
  }
  const cache = await caches.open(SAVED_CACHE);
  let done = 0;
  let failed = 0;
  let bytes = 0;
  let next = 0;
  const worker = async () => {
    while (next < urls.length) {
      if (opts.signal?.aborted) throw new DOMException("Stopped", "AbortError");
      const url = urls[next++];
      const key = tileKey(url);
      try {
        if (!(await cache.match(key))) {
          // "no-store" tells the service worker this is a save: it goes straight to the network and isn't
          // also copied into the recently-viewed cache.
          const res = await fetch(url, { mode: "cors", cache: "no-store", signal: opts.signal });
          if (!res.ok) throw new Error(String(res.status));
          const blob = await res.clone().blob();
          bytes += blob.size;
          await cache.put(key, res);
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") throw e;
        failed++;
      }
      opts.onProgress?.(++done, urls.length);
    }
  };
  await Promise.all(Array.from({ length: 6 }, worker));
  const area: SavedArea = {
    id: `${Date.now().toString(36)}-${Math.round(bbox[0] * 1000)}`,
    name,
    bbox,
    minZoom: opts.minZoom ?? 10,
    tiles: urls.length - failed,
    failed,
    bytes,
    savedAt: Date.now(),
  };
  save(AREAS_KEY, [...listAreas().filter((a) => a.name !== name), area]);
  return area;
}

/** Remove an area's tiles, keeping any that another saved area still needs. */
export async function deleteArea(id: string): Promise<void> {
  const areas = listAreas();
  const gone = areas.find((a) => a.id === id);
  const rest = areas.filter((a) => a.id !== id);
  save(AREAS_KEY, rest);
  if (!gone || !offlineSupported()) return;
  const keep = new Set(rest.flatMap((a) => areaUrls(a.bbox, a.minZoom).map(tileKey)));
  const cache = await caches.open(SAVED_CACHE);
  await Promise.all(areaUrls(gone.bbox, gone.minZoom).map(tileKey).filter((k) => !keep.has(k)).map((k) => cache.delete(k)));
}

export async function storageUse(): Promise<{ usedMb: number; quotaMb: number } | null> {
  try {
    const e = await navigator.storage?.estimate?.();
    if (!e) return null;
    return { usedMb: Math.round((e.usage ?? 0) / 1048576), quotaMb: Math.round((e.quota ?? 0) / 1048576) };
  } catch {
    return null;
  }
}
