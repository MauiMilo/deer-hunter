// Wind direction math. Directions are meteorological: the direction the wind blows FROM,
// in degrees clockwise from north. Averaging angles needs circular statistics
// (350 deg and 10 deg average to 0, not 180).

const RAD = Math.PI / 180;
const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
const NAMES: Record<string, string> = {
  N: "north", NE: "northeast", E: "east", SE: "southeast", S: "south", SW: "southwest", W: "west", NW: "northwest",
};

export function normalizeDeg(d: number): number {
  return ((d % 360) + 360) % 360;
}

export function compass(deg: number, points: 8 | 16 = 16): string {
  const n = normalizeDeg(deg);
  if (points === 8) {
    const eight = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    return eight[Math.round(n / 45) % 8];
  }
  return POINTS[Math.round(n / 22.5) % 16];
}

export function compassName(deg: number): string {
  return NAMES[compass(deg, 8)];
}

/** Smallest angle between two directions, 0-180. */
export function angleDiff(a: number, b: number): number {
  const d = Math.abs(normalizeDeg(a) - normalizeDeg(b));
  return d > 180 ? 360 - d : d;
}

/** Where your scent goes: downwind is opposite the "from" direction. */
export function downwind(fromDeg: number): number {
  return normalizeDeg(fromDeg + 180);
}

export interface CircularSummary {
  meanDeg: number | null; // null when directions cancel out (no prevailing direction)
  /** 0 = directions all over the place, 1 = perfectly steady. */
  steadiness: number;
  n: number;
}

/**
 * Circular mean of wind directions, optionally weighted (e.g., by speed so calm, swirling
 * readings count less). Steadiness is the mean resultant length R.
 */
export function circularMean(degs: number[], weights?: number[]): CircularSummary {
  let sx = 0, sy = 0, sw = 0;
  degs.forEach((d, i) => {
    const w = weights ? Math.max(0, weights[i] ?? 0) : 1;
    sx += w * Math.cos(d * RAD);
    sy += w * Math.sin(d * RAD);
    sw += w;
  });
  if (sw === 0) return { meanDeg: null, steadiness: 0, n: degs.length };
  const R = Math.hypot(sx, sy) / sw;
  if (R < 1e-9) return { meanDeg: null, steadiness: 0, n: degs.length };
  return { meanDeg: normalizeDeg(Math.atan2(sy, sx) / RAD), steadiness: R, n: degs.length };
}

/** Circular standard deviation in degrees (Mardia): spread of directions. */
export function circularSpreadDeg(steadiness: number): number {
  if (steadiness <= 0) return 180;
  if (steadiness >= 1) return 0;
  return Math.min(180, Math.sqrt(-2 * Math.log(steadiness)) / RAD);
}

/** Counts per compass sector (for a wind rose). */
export function sectorCounts(degs: number[], sectors = 8): number[] {
  const out = new Array(sectors).fill(0);
  const width = 360 / sectors;
  for (const d of degs) out[Math.round(normalizeDeg(d) / width) % sectors]++;
  return out;
}

/**
 * Is a wind OK for a setup where deer are expected to come from `deerFromDeg`?
 * Good when your scent blows away from that direction (wind blowing from the deer toward you,
 * or crosswind). `toleranceDeg` is how far off dead-ahead is still acceptable.
 */
export function windFavorsSetup(windFromDeg: number, deerFromDeg: number, toleranceDeg = 60): "good" | "marginal" | "bad" {
  // Scent travels toward downwind(windFrom). Bad if that points at the deer.
  const scentToDeer = angleDiff(downwind(windFromDeg), deerFromDeg);
  if (scentToDeer >= 180 - toleranceDeg) return "good";
  if (scentToDeer > 45) return "marginal";
  return "bad";
}
