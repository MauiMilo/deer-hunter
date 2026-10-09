// Sunrise and sunset from the NOAA solar position equations (accurate to about a minute
// at these latitudes). Used for legal shooting hours, which NH defines relative to sunrise/sunset.

const RAD = Math.PI / 180;

function julianDay(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}

/**
 * Sunrise/sunset for the calendar day `ymd` (YYYY-MM-DD) at lat/lon.
 * Returns UTC Date objects, or null when the sun doesn't rise/set (not an issue in NH).
 */
export function sunTimes(ymd: string, lat: number, lon: number): { sunrise: Date; sunset: Date } | null {
  const [y, m, d] = ymd.split("-").map(Number);
  // Solar noon in UTC is roughly 12:00 - lon/15 hours; iterate twice for accuracy.
  const zenith = 90.833; // official sunrise/sunset includes refraction and the sun's radius
  const calc = (rising: boolean): Date | null => {
    let t = Date.UTC(y, m - 1, d, 12) - (lon / 15) * 3600000;
    for (let i = 0; i < 3; i++) {
      const jd = julianDay(new Date(t));
      const jc = (jd - 2451545) / 36525;
      const L0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360;
      const M = 357.52911 + jc * (35999.05029 - 0.0001537 * jc);
      const e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc);
      const C =
        Math.sin(M * RAD) * (1.914602 - jc * (0.004817 + 0.000014 * jc)) +
        Math.sin(2 * M * RAD) * (0.019993 - 0.000101 * jc) +
        Math.sin(3 * M * RAD) * 0.000289;
      const trueLong = L0 + C;
      const omega = 125.04 - 1934.136 * jc;
      const lambda = trueLong - 0.00569 - 0.00478 * Math.sin(omega * RAD);
      const eps0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60;
      const eps = eps0 + 0.00256 * Math.cos(omega * RAD);
      const decl = Math.asin(Math.sin(eps * RAD) * Math.sin(lambda * RAD)) / RAD;
      const yv = Math.tan((eps / 2) * RAD) ** 2;
      const eqTime =
        (4 / RAD) *
        (yv * Math.sin(2 * L0 * RAD) -
          2 * e * Math.sin(M * RAD) +
          4 * e * yv * Math.sin(M * RAD) * Math.cos(2 * L0 * RAD) -
          0.5 * yv * yv * Math.sin(4 * L0 * RAD) -
          1.25 * e * e * Math.sin(2 * M * RAD)); // minutes
      const cosH =
        Math.cos(zenith * RAD) / (Math.cos(lat * RAD) * Math.cos(decl * RAD)) -
        Math.tan(lat * RAD) * Math.tan(decl * RAD);
      if (cosH > 1 || cosH < -1) return null;
      const H = Math.acos(cosH) / RAD; // degrees
      const noonMin = 720 - 4 * lon - eqTime; // minutes after 00:00 UTC
      const minutes = noonMin + (rising ? -4 * H : 4 * H);
      t = Date.UTC(y, m - 1, d) + minutes * 60000;
    }
    return new Date(t);
  };
  const sunrise = calc(true);
  const sunset = calc(false);
  if (!sunrise || !sunset) return null;
  return { sunrise, sunset };
}

export function legalHours(
  ymd: string,
  lat: number,
  lon: number,
  beforeMin = 30,
  afterMin = 30,
): { start: Date; end: Date; sunrise: Date; sunset: Date } | null {
  const s = sunTimes(ymd, lat, lon);
  if (!s) return null;
  return {
    start: new Date(s.sunrise.getTime() - beforeMin * 60000),
    end: new Date(s.sunset.getTime() + afterMin * 60000),
    sunrise: s.sunrise,
    sunset: s.sunset,
  };
}

export function formatClock(d: Date, timeZone = "America/New_York"): string {
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone });
}
