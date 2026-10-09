// Distance helpers. Straight-line distance only; drive times need a routing service.

const R_MILES = 3958.7613;
const RAD = Math.PI / 180;

export function haversineMiles(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const dLat = (lat2 - lat1) * RAD;
  const dLon = (lon2 - lon1) * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * RAD) * Math.cos(lat2 * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * R_MILES * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Bearing in degrees clockwise from north, from a to b. */
export function bearingDeg(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a.map((v) => v * RAD);
  const [lon2, lat2] = b.map((v) => v * RAD);
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  return ((Math.atan2(y, x) / RAD) + 360) % 360;
}

/**
 * Very rough drive time: straight-line miles x 1.35 road factor at 40 mph average.
 * Northern NH back roads are slow and many logging roads are gated, so this is a planning
 * guess only and is always labeled as such.
 */
export function roughDriveMinutes(miles: number): number {
  return Math.round(((miles * 1.35) / 40) * 60);
}
