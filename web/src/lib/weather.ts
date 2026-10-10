// Forecasts from Open-Meteo (free for non-commercial use, CC BY 4.0, called straight from the phone).
// https://open-meteo.com/en/docs

export interface Hour {
  t: number; // epoch ms (UTC)
  tempF: number | null;
  precipIn: number | null;
  code: number | null; // WMO weather code
  windMph: number | null;
  windFromDeg: number | null;
  gustMph: number | null;
}

export interface PointForecast {
  key: string;
  lat: number;
  lon: number;
  hours: Hour[];
}

export interface ForecastResult {
  points: PointForecast[];
  fetchedAt: number;
  error?: string;
}

const ENDPOINT = "https://api.open-meteo.com/v1/forecast";
const HOURLY = "temperature_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m";
const CACHE_KEY = "ds.forecast.v2";
const CACHE_MS = 60 * 60 * 1000;

/** Snap a point to a coarse grid so nearby blocks share one forecast request. */
export function cellKey(lon: number, lat: number, step = 0.2): string {
  const r = (v: number) => (Math.round(v / step) * step).toFixed(2);
  return `${r(lat)},${r(lon)}`;
}

export function buildUrl(points: { lat: number; lon: number }[], days = 7): string {
  const p = new URLSearchParams({
    latitude: points.map((x) => x.lat.toFixed(3)).join(","),
    longitude: points.map((x) => x.lon.toFixed(3)).join(","),
    hourly: HOURLY,
    temperature_unit: "fahrenheit",
    wind_speed_unit: "mph",
    precipitation_unit: "inch",
    timeformat: "unixtime",
    timezone: "America/New_York",
    forecast_days: String(days),
  });
  return `${ENDPOINT}?${p.toString()}`;
}

type Raw = {
  latitude: number;
  longitude: number;
  hourly?: Record<string, (number | null)[]>;
  error?: boolean;
  reason?: string;
};

export function parseResponse(json: unknown, keys: string[]): PointForecast[] {
  if (json && typeof json === "object" && !Array.isArray(json) && (json as Raw).error) {
    throw new Error((json as Raw).reason || "forecast service error");
  }
  const arr: Raw[] = Array.isArray(json) ? (json as Raw[]) : [json as Raw];
  if (arr.length !== keys.length) throw new Error(`expected ${keys.length} forecasts, got ${arr.length}`);
  return arr.map((r, i) => {
    const h = r.hourly ?? {};
    const times = (h.time ?? []) as number[];
    const col = (name: string, j: number) => {
      const v = h[name]?.[j];
      return typeof v === "number" && Number.isFinite(v) ? v : null;
    };
    return {
      key: keys[i],
      lat: r.latitude,
      lon: r.longitude,
      hours: times.map((t, j) => ({
        t: t * 1000,
        tempF: col("temperature_2m", j),
        precipIn: col("precipitation", j),
        code: col("weather_code", j),
        windMph: col("wind_speed_10m", j),
        windFromDeg: col("wind_direction_10m", j),
        gustMph: col("wind_gusts_10m", j),
      })),
    };
  });
}

// Each 0.2-degree cell's forecast is saved on the phone with the time it was fetched. Fresh ones
// (under an hour) are reused; with no signal, saved ones up to STALE_MS old are shown, labeled.
type Saved = Record<string, { point: PointForecast; fetchedAt: number }>;
const STALE_MS = 7 * 24 * 60 * 60 * 1000;

function readCache(): Saved {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) && !("points" in parsed) ? (parsed as Saved) : {};
  } catch {
    return {};
  }
}

function writeCache(saved: Saved) {
  const now = Date.now();
  const kept: Saved = {};
  for (const [k, v] of Object.entries(saved)) if (now - v.fetchedAt < STALE_MS) kept[k] = v;
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(kept));
  } catch {
    /* storage full or blocked: forecast still works, just not saved */
  }
}

function fromSaved(saved: Saved, keys: string[], maxAge: number): ForecastResult | null {
  const now = Date.now();
  const hits = keys.map((k) => saved[k]).filter((v) => v && now - v.fetchedAt < maxAge);
  if (!hits.length) return null;
  return { points: hits.map((h) => h.point), fetchedAt: Math.min(...hits.map((h) => h.fetchedAt)) };
}

function ago(ms: number): string {
  const h = Math.round((Date.now() - ms) / 3600000);
  if (h < 1) return "less than an hour ago";
  if (h < 48) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return `${Math.round(h / 24)} days ago`;
}

export async function fetchForecasts(cells: Map<string, { lat: number; lon: number }>, fetchImpl: typeof fetch = fetch): Promise<ForecastResult> {
  const keys = [...cells.keys()];
  if (!keys.length) return { points: [], fetchedAt: Date.now() };
  const saved = readCache();
  const fresh = fromSaved(saved, keys, CACHE_MS);
  if (fresh && fresh.points.length === keys.length) return fresh;
  try {
    const res = await fetchImpl(buildUrl(keys.map((k) => cells.get(k)!)));
    const json = await res.json();
    if (!res.ok) throw new Error((json as Raw)?.reason || `HTTP ${res.status}`);
    const fetchedAt = Date.now();
    const points = parseResponse(json, keys);
    for (const p of points) saved[p.key] = { point: p, fetchedAt };
    writeCache(saved);
    return { points, fetchedAt };
  } catch (e) {
    const old = fromSaved(saved, keys, STALE_MS);
    if (old) return { ...old, error: `No connection (${(e as Error).message}). Showing the forecast saved ${ago(old.fetchedAt)}.` };
    return { points: [], fetchedAt: Date.now(), error: `Forecast unavailable: ${(e as Error).message}` };
  }
}

const CODE_TEXT: Record<number, string> = {
  0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
  51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
  61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
  71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Rain showers", 81: "Rain showers",
  82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail",
  99: "Thunderstorm with hail",
};

export function describeCode(code: number | null): string {
  return code === null ? "Unknown" : CODE_TEXT[code] ?? `Code ${code}`;
}
