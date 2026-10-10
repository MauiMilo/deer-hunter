import { describe, expect, it } from "vitest";
import { hoursInWindow, windowBounds } from "../conditions";
import { buildUrl, cellKey, fetchForecasts, parseResponse } from "../weather";

const raw = (lat: number, lon: number) => ({
  latitude: lat,
  longitude: lon,
  hourly: {
    time: [1791633600, 1791637200],
    temperature_2m: [38.1, 40.2],
    precipitation: [0, 0.01],
    weather_code: [1, 3],
    wind_speed_10m: [6.2, 8.4],
    wind_direction_10m: [300, 310],
    wind_gusts_10m: [12, null],
  },
});

describe("forecast parsing", () => {
  it("handles one location (object) and several (array)", () => {
    expect(parseResponse(raw(45, -71.4), ["a"])[0].hours).toHaveLength(2);
    const many = parseResponse([raw(45, -71.4), raw(45.2, -71.2)], ["a", "b"]);
    expect(many.map((p) => p.key)).toEqual(["a", "b"]);
    expect(many[0].hours[1].gustMph).toBeNull();
    expect(many[0].hours[0].t).toBe(1791633600 * 1000);
  });

  it("raises on service errors and count mismatches", () => {
    expect(() => parseResponse({ error: true, reason: "Bad lat" }, ["a"])).toThrow("Bad lat");
    expect(() => parseResponse([raw(1, 1)], ["a", "b"])).toThrow(/expected 2/);
  });

  it("builds a request in US units with unambiguous timestamps", () => {
    const url = new URL(buildUrl([{ lat: 45.05, lon: -71.4 }, { lat: 45.2, lon: -71.2 }]));
    expect(url.searchParams.get("latitude")).toBe("45.050,45.200");
    expect(url.searchParams.get("wind_speed_unit")).toBe("mph");
    expect(url.searchParams.get("timeformat")).toBe("unixtime");
  });

  it("snaps nearby points to the same cell", () => {
    expect(cellKey(-71.41, 45.04)).toBe(cellKey(-71.39, 45.06));
  });

  it("falls back to a saved forecast when there's no signal", async () => {
    const store: Record<string, string> = {};
    const ls = { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => void (store[k] = v) };
    const orig = (globalThis as { localStorage?: unknown }).localStorage;
    (globalThis as { localStorage?: unknown }).localStorage = ls;
    try {
      const cells = new Map([["45.00,-71.40", { lat: 45, lon: -71.4 }]]);
      const body = { latitude: 45, longitude: -71.4, hourly: { time: [1760000000], temperature_2m: [40], precipitation: [0], weather_code: [2], wind_speed_10m: [5], wind_direction_10m: [300], wind_gusts_10m: [9] } };
      const ok = (() => Promise.resolve({ ok: true, json: () => Promise.resolve(body) })) as unknown as typeof fetch;
      const first = await fetchForecasts(cells, ok);
      expect(first.points).toHaveLength(1);
      // Two hours later with no signal: the saved forecast comes back, labeled.
      const saved = JSON.parse(store["ds.forecast.v2"]);
      saved["45.00,-71.40"].fetchedAt -= 2 * 3600 * 1000;
      store["ds.forecast.v2"] = JSON.stringify(saved);
      const failing = (() => Promise.reject(new Error("offline"))) as unknown as typeof fetch;
      const r = await fetchForecasts(cells, failing);
      expect(r.points).toHaveLength(1);
      expect(r.error).toMatch(/saved 2 hours ago/);
    } finally {
      (globalThis as { localStorage?: unknown }).localStorage = orig;
    }
  });

  it("returns an error instead of throwing when the network fails", async () => {
    const cells = new Map([["x", { lat: 45, lon: -71 }]]);
    const failing = (() => Promise.reject(new Error("offline"))) as unknown as typeof fetch;
    const r = await fetchForecasts(cells, failing);
    expect(r.points).toEqual([]);
    expect(r.error).toMatch(/offline/);
  });
});

describe("time windows", () => {
  const start = new Date(Date.UTC(2026, 9, 10, 10, 30));
  const end = new Date(Date.UTC(2026, 9, 10, 22, 45));

  it("uses the first and last three legal hours", () => {
    expect(windowBounds("morning", start, end)).toEqual([start.getTime(), start.getTime() + 3 * 3600000]);
    expect(windowBounds("evening", start, end)).toEqual([end.getTime() - 3 * 3600000, end.getTime()]);
    expect(windowBounds("allday", start, end)).toEqual([start.getTime(), end.getTime()]);
  });

  it("includes hours that overlap the window", () => {
    const h = (iso: string) => ({ t: Date.parse(iso), tempF: 1, precipIn: 0, code: 0, windMph: 1, windFromDeg: 0, gustMph: 1 });
    const hours = [h("2026-10-10T09:00Z"), h("2026-10-10T10:00Z"), h("2026-10-10T13:00Z"), h("2026-10-10T14:00Z")];
    const inWin = hoursInWindow(hours, windowBounds("morning", start, end));
    expect(inWin.map((x) => new Date(x.t).getUTCHours())).toEqual([10, 13]);
  });
});
