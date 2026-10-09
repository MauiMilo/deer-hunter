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
const CACHE_KEY = "ds.forecast.v1";
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

function readCache(): ForecastResult | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ForecastResult;
    return Date.now() - parsed.fetchedAt < CACHE_MS ? parsed : null;
  } catch {
    return null;
  }
}

function writeCache(r: ForecastResult) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(r));
  } catch {
    /* storage full or blocked: forecast still works, just not cached */
  }
}

export async function fetchForecasts(cells: Map<string, { lat: number; lon: number }>, fetchImpl: typeof fetch = fetch): Promise<ForecastResult> {
  const keys = [...cells.keys()];
  const cached = readCache();
  if (cached && keys.every((k) => cached.points.some((p) => p.key === k))) return cached;
  if (!keys.length) return { points: [], fetchedAt: Date.now() };
  try {
    const res = await fetchImpl(buildUrl(keys.map((k) => cells.get(k)!)));
    const json = await res.json();
    if (!res.ok) throw new Error((json as Raw)?.reason || `HTTP ${res.status}`);
    const out = { points: parseResponse(json, keys), fetchedAt: Date.now() };
    writeCache(out);
    return out;
  } catch (e) {
    if (cached) return { ...cached, error: `Showing an older forecast: ${(e as Error).message}` };
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
