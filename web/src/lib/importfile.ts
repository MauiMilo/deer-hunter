// Read your own GPX, KML or GeoJSON files (from onX, Gaia, a GPS unit, Google Earth...) into map
// features. Everything stays on the phone. Pure functions: no browser APIs, so they run in tests.
//
// Not supported: KMZ (zipped KML; unzip it first) and map overlays/images inside KML.

export interface ImportedFeature {
  type: "Feature";
  geometry:
    | { type: "Point"; coordinates: [number, number] }
    | { type: "LineString"; coordinates: [number, number][] }
    | { type: "Polygon"; coordinates: [number, number][][] };
  properties: { name: string; layer?: string };
}

export interface ImportResult {
  features: ImportedFeature[];
  points: number;
  lines: number;
  areas: number;
  warnings: string[];
}

export const MAX_FILE_BYTES = 3_000_000;
const MAX_LINE_POINTS = 1500;
const MAX_FEATURES = 3000;

const T = "(?:[\\w-]+:)?"; // optional XML namespace prefix

function textOf(block: string, tag: string): string {
  const m = block.match(new RegExp(`<${T}${tag}\\b[^>]*>([\\s\\S]*?)</${T}${tag}>`, "i"));
  if (!m) return "";
  return m[1]
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/<[^>]+>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .trim();
}

function blocks(xml: string, tag: string): string[] {
  return xml.match(new RegExp(`<${T}${tag}\\b[\\s\\S]*?</${T}${tag}>`, "gi")) ?? [];
}

function attr(openTag: string, name: string): number | null {
  const m = openTag.match(new RegExp(`\\b${name}\\s*=\\s*["']([^"']+)["']`, "i"));
  const v = m ? Number(m[1]) : NaN;
  return Number.isFinite(v) ? v : null;
}

function validLonLat(lon: number | null, lat: number | null): lon is number {
  return lon !== null && lat !== null && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
}

/** Keep every nth point so long tracks stay small enough to store on the phone. */
function thin(pts: [number, number][]): [number, number][] {
  if (pts.length <= MAX_LINE_POINTS) return pts;
  const step = Math.ceil(pts.length / MAX_LINE_POINTS);
  const out = pts.filter((_, i) => i % step === 0);
  if (out[out.length - 1] !== pts[pts.length - 1]) out.push(pts[pts.length - 1]);
  return out;
}

function gpxPoints(xml: string, tag: string): { lon: number; lat: number; name: string }[] {
  const re = new RegExp(`<${T}${tag}\\b([^>]*?)(/>|>([\\s\\S]*?)</${T}${tag}>)`, "gi");
  const out = [];
  for (const m of xml.matchAll(re)) {
    const lat = attr(m[1], "lat");
    const lon = attr(m[1], "lon");
    if (validLonLat(lon, lat)) out.push({ lon, lat: lat as number, name: m[3] ? textOf(m[3], "name") : "" });
  }
  return out;
}

export function parseGpx(xml: string): ImportedFeature[] {
  const out: ImportedFeature[] = [];
  const noTracks = xml.replace(new RegExp(`<${T}(trk|rte)\\b[\\s\\S]*?</${T}\\1>`, "gi"), "");
  for (const p of gpxPoints(noTracks, "wpt")) {
    out.push({ type: "Feature", geometry: { type: "Point", coordinates: [p.lon, p.lat] }, properties: { name: p.name || "Waypoint" } });
  }
  for (const trk of blocks(xml, "trk")) {
    const name = textOf(trk.replace(new RegExp(`<${T}trkseg\\b[\\s\\S]*?</${T}trkseg>`, "gi"), ""), "name") || "Track";
    for (const seg of blocks(trk, "trkseg")) {
      const pts = gpxPoints(seg, "trkpt").map((p) => [p.lon, p.lat] as [number, number]);
      if (pts.length >= 2) out.push({ type: "Feature", geometry: { type: "LineString", coordinates: thin(pts) }, properties: { name } });
    }
  }
  for (const rte of blocks(xml, "rte")) {
    const name = textOf(rte.replace(new RegExp(`<${T}rtept\\b[\\s\\S]*?(/>|</${T}rtept>)`, "gi"), ""), "name") || "Route";
    const pts = gpxPoints(rte, "rtept").map((p) => [p.lon, p.lat] as [number, number]);
    if (pts.length >= 2) out.push({ type: "Feature", geometry: { type: "LineString", coordinates: thin(pts) }, properties: { name } });
  }
  return out;
}

function kmlCoords(s: string): [number, number][] {
  return s
    .trim()
    .split(/\s+/)
    .map((t) => t.split(",").map(Number))
    .filter((c) => c.length >= 2 && validLonLat(c[0], c[1]))
    .map((c) => [c[0], c[1]] as [number, number]);
}

export function parseKml(xml: string): ImportedFeature[] {
  const out: ImportedFeature[] = [];
  for (const pm of blocks(xml, "Placemark")) {
    const geomFree = pm.replace(new RegExp(`<${T}(Point|LineString|Polygon|MultiGeometry|Track)\\b[\\s\\S]*?</${T}\\1>`, "gi"), "");
    const name = textOf(geomFree, "name") || "Placemark";
    for (const pt of blocks(pm, "Point")) {
      const c = kmlCoords(textOf(pt, "coordinates"))[0];
      if (c) out.push({ type: "Feature", geometry: { type: "Point", coordinates: c }, properties: { name } });
    }
    for (const ls of blocks(pm, "LineString")) {
      const c = kmlCoords(textOf(ls, "coordinates"));
      if (c.length >= 2) out.push({ type: "Feature", geometry: { type: "LineString", coordinates: thin(c) }, properties: { name } });
    }
    for (const pg of blocks(pm, "Polygon")) {
      const outer = blocks(pg, "outerBoundaryIs")[0] ?? pg;
      const c = kmlCoords(textOf(outer, "coordinates"));
      if (c.length >= 4) out.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [thin(c)] }, properties: { name } });
    }
    for (const tr of blocks(pm, "Track")) {
      const c = [...tr.matchAll(new RegExp(`<${T}coord\\b[^>]*>([^<]+)</${T}coord>`, "gi"))]
        .map((m) => m[1].trim().split(/\s+/).map(Number))
        .filter((v) => v.length >= 2 && validLonLat(v[0], v[1]))
        .map((v) => [v[0], v[1]] as [number, number]);
      if (c.length >= 2) out.push({ type: "Feature", geometry: { type: "LineString", coordinates: thin(c) }, properties: { name } });
    }
  }
  return out;
}

type AnyGeom = { type: string; coordinates?: unknown; geometries?: AnyGeom[] };

export function parseGeoJson(text: string): ImportedFeature[] {
  const doc = JSON.parse(text) as { type?: string; features?: { geometry: AnyGeom; properties?: Record<string, unknown> }[] } & AnyGeom;
  const feats =
    doc.type === "FeatureCollection" ? doc.features ?? [] : doc.type === "Feature" ? [doc as unknown as { geometry: AnyGeom; properties?: Record<string, unknown> }] : [{ geometry: doc, properties: {} }];
  const out: ImportedFeature[] = [];
  const add = (g: AnyGeom | null | undefined, name: string) => {
    if (!g) return;
    const c = g.coordinates as never;
    if (g.type === "Point") out.push({ type: "Feature", geometry: { type: "Point", coordinates: [c[0], c[1]] }, properties: { name } });
    else if (g.type === "MultiPoint") (c as [number, number][]).forEach((p) => add({ type: "Point", coordinates: p }, name));
    else if (g.type === "LineString") out.push({ type: "Feature", geometry: { type: "LineString", coordinates: thin((c as number[][]).map((p) => [p[0], p[1]])) }, properties: { name } });
    else if (g.type === "MultiLineString") (c as number[][][]).forEach((l) => add({ type: "LineString", coordinates: l }, name));
    else if (g.type === "Polygon") out.push({ type: "Feature", geometry: { type: "Polygon", coordinates: [thin((c as number[][][])[0].map((p) => [p[0], p[1]]))] }, properties: { name } });
    else if (g.type === "MultiPolygon") (c as number[][][][]).forEach((p) => add({ type: "Polygon", coordinates: p }, name));
    else if (g.type === "GeometryCollection") (g.geometries ?? []).forEach((x) => add(x, name));
  };
  for (const f of feats) add(f.geometry, String(f.properties?.name ?? f.properties?.title ?? "Feature"));
  return out;
}

export function parseFile(fileName: string, text: string): ImportResult {
  const lower = fileName.toLowerCase();
  const warnings: string[] = [];
  let features: ImportedFeature[];
  if (lower.endsWith(".kmz")) throw new Error("KMZ files are zipped. Unzip it (or export as KML or GPX) and import that instead.");
  if (lower.endsWith(".gpx") || /<gpx\b/i.test(text.slice(0, 2000))) features = parseGpx(text);
  else if (lower.endsWith(".kml") || /<kml\b/i.test(text.slice(0, 2000))) features = parseKml(text);
  else if (lower.endsWith(".geojson") || lower.endsWith(".json") || text.trim().startsWith("{")) features = parseGeoJson(text);
  else throw new Error("Pick a .gpx, .kml or .geojson file.");
  if (features.length > MAX_FEATURES) {
    warnings.push(`Only the first ${MAX_FEATURES.toLocaleString()} of ${features.length.toLocaleString()} items were kept.`);
    features = features.slice(0, MAX_FEATURES);
  }
  if (!features.length) throw new Error("No waypoints, tracks or areas were found in that file.");
  return {
    features,
    points: features.filter((f) => f.geometry.type === "Point").length,
    lines: features.filter((f) => f.geometry.type === "LineString").length,
    areas: features.filter((f) => f.geometry.type === "Polygon").length,
    warnings,
  };
}
