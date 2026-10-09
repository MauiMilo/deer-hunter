// Waypoints and hunt observations, kept only on this phone. Pure helpers (storage lives in the hook).

export const WAYPOINT_KINDS = ["Sign", "Rub", "Scrape", "Tracks", "Bed", "Deer seen", "Stand", "Parking", "Other"] as const;
export type WaypointKind = (typeof WAYPOINT_KINDS)[number];

export interface Waypoint {
  id: string;
  kind: WaypointKind;
  name: string;
  lon: number;
  lat: number;
  accuracyM: number | null;
  at: string; // ISO time
  note: string;
}

export interface Observation {
  id: string;
  date: string; // YYYY-MM-DD
  window: "morning" | "evening" | "allday";
  placeId: string | null; // unit or property id
  placeName: string;
  deerSeen: number;
  hours: number;
  note: string;
}

export function newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** GPX 1.1 file with one waypoint per entry (opens in onX, Gaia, Google Earth, etc.). */
export function toGpx(points: Waypoint[]): string {
  const wpts = points
    .map(
      (p) =>
        `  <wpt lat="${p.lat.toFixed(6)}" lon="${p.lon.toFixed(6)}">\n` +
        `    <time>${esc(p.at)}</time>\n    <name>${esc(p.name || p.kind)}</name>\n` +
        `    <desc>${esc([p.kind, p.note].filter(Boolean).join(": "))}</desc>\n    <type>${esc(p.kind)}</type>\n  </wpt>`,
    )
    .join("\n");
  return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Deer Scout" xmlns="http://www.topografix.com/GPX/1/1">\n${wpts}\n</gpx>\n`;
}

/** Sightings per hour, the simplest fair comparison between places you've hunted. */
export function sightingRate(obs: Observation[]): { hours: number; deer: number; perHour: number | null; sits: number } {
  const hours = obs.reduce((a, o) => a + Math.max(0, o.hours), 0);
  const deer = obs.reduce((a, o) => a + Math.max(0, o.deerSeen), 0);
  return { hours, deer, perHour: hours > 0 ? deer / hours : null, sits: obs.length };
}

export function waypointsGeoJson(points: Waypoint[]) {
  return {
    type: "FeatureCollection" as const,
    features: points.map((p) => ({
      type: "Feature" as const,
      geometry: { type: "Point" as const, coordinates: [p.lon, p.lat] },
      properties: { id: p.id, kind: p.kind, name: p.name || p.kind },
    })),
  };
}
