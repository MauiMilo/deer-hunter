import { describe, expect, it } from "vitest";
import { scoreConditions } from "../conditions";
import { bestPerProperty, rank, reweight, travelScore } from "../rank";
import { nextOpening, seasonStatus } from "../seasons";
import { catalog, property, regs, unit } from "./fixtures";

describe("seasons", () => {
  it("knows WMU A archery closes Dec 8 while B runs to Dec 15", () => {
    expect(seasonStatus(regs, "2026-12-10", "archery", ["A"]).open).toBe(false);
    expect(seasonStatus(regs, "2026-12-10", "archery", ["B"]).open).toBe(true);
  });

  it("treats a split town conservatively", () => {
    const s = seasonStatus(regs, "2026-12-10", "archery", ["A", "B"]);
    expect(s.open).toBe(false);
    expect(s.message).toMatch(/only some/);
    expect(s.certainty).toBe("split-unit");
  });

  it("applies the stricter deer rule across candidate units", () => {
    expect(seasonStatus(regs, "2026-11-11", "firearm", ["A"]).deer).toBe("any");
    expect(seasonStatus(regs, "2026-11-12", "firearm", ["A"]).deer).toBe("antlered");
  });

  it("refuses to guess without a unit", () => {
    const s = seasonStatus(regs, "2026-10-10", "archery", []);
    expect(s.open).toBe(false);
    expect(s.certainty).toBe("unknown-unit");
  });

  it("finds the next opening", () => {
    expect(nextOpening(regs, "2026-10-10", "muzzleloader", ["A"])).toBe("2026-10-31");
    expect(nextOpening(regs, "2026-12-01", "firearm", ["A"])).toBeNull();
  });
});

describe("conditions", () => {
  const hour = (o: Partial<{ windMph: number; gustMph: number; precipIn: number; code: number; tempF: number; windFromDeg: number }> = {}) => ({
    t: 0, tempF: o.tempF ?? 40, precipIn: o.precipIn ?? 0, code: o.code ?? 1, windMph: o.windMph ?? 5, windFromDeg: o.windFromDeg ?? 315, gustMph: o.gustMph ?? 10,
  });

  it("scores a calm dry morning at 100", () => {
    const c = scoreConditions([hour(), hour(), hour()])!;
    expect(c.score).toBe(100);
    expect(c.safety).toEqual([]);
    expect(c.wind.fromDeg).toBeCloseTo(315, 6);
    expect(c.wind.steady).toBe(true);
  });

  it("penalizes wind and rain modestly", () => {
    expect(scoreConditions([hour({ windMph: 17 })])!.score).toBe(85);
    expect(scoreConditions([hour({ precipIn: 0.3 })])!.score).toBe(85);
    expect(scoreConditions([hour({ precipIn: 0.6 })])!.score).toBe(70);
  });

  it("flags dangerous weather", () => {
    const gust = scoreConditions([hour({ gustMph: 40 })])!;
    expect(gust.safety[0]).toMatch(/falling limbs/);
    const storm = scoreConditions([hour({ code: 95 })])!;
    expect(storm.score).toBe(60);
    expect(storm.safety[0]).toMatch(/lightning/);
  });

  it("returns null with no hours", () => {
    expect(scoreConditions([])).toBeNull();
  });
});

describe("ranking", () => {
  const props = [property("open", "verified"), property("maybe", "unknown"), property("closed", "prohibited"), property("bigopen", "verified")];
  const units = [
    unit("open", "open", 50, [-71.4, 45.05]),
    unit("maybe", "maybe", 90, [-71.4, 45.06]),
    unit("closed", "closed", 99, [-71.4, 45.07]),
    unit("bigopen", "bigopen", 80, [-71.45, 45.1]),
  ];
  const cat = catalog(units, props);

  it("never shows prohibited land and hides unknown land by default", () => {
    const out = rank({ catalog: cat, regs, ymd: "2026-10-10", method: "archery", origin: null, includeUnknown: false });
    expect(out.ranked.map((r) => r.unit.id)).toEqual(["bigopen", "open"]);
    expect(out.excluded).toEqual({ prohibited: 1, unknown: 1, closed: 0 });
  });

  it("lists research candidates after verified land", () => {
    const out = rank({ catalog: cat, regs, ymd: "2026-10-10", method: "archery", origin: null, includeUnknown: true });
    expect(out.ranked.map((r) => r.unit.id)).toEqual(["bigopen", "open", "maybe"]);
  });

  it("drops units whose season is closed that day", () => {
    const out = rank({ catalog: cat, regs, ymd: "2026-10-10", method: "firearm", origin: null, includeUnknown: false });
    expect(out.ranked).toEqual([]);
    expect(out.excluded.closed).toBe(2);
  });

  it("factors in travel when a location is known", () => {
    const near = [-71.4, 45.05] as [number, number];
    const out = rank({ catalog: cat, regs, ymd: "2026-10-10", method: "archery", origin: near, includeUnknown: false });
    const open = out.ranked.find((r) => r.unit.id === "open")!;
    expect(open.miles).toBeLessThan(0.01);
    expect(open.parts.map((p) => p.label)).toEqual(["Property quality", "Travel"]);
  });

  it("recomputes quality with custom weights, ignoring missing factors", () => {
    expect(reweight(units[0], { habitat: 0.9, access: 0.1 })).toBe(50);
    expect(reweight(units[0], { habitat: 0.9, access: 0 })).toBeNull();
  });

  it("keeps only the best block of each property", () => {
    const blocks = [unit("big~A1", "bigopen", 70, [-71.45, 45.1]), unit("big~A2", "bigopen", 60, [-71.45, 45.1]), ...units];
    const out = rank({ catalog: catalog(blocks, props), regs, ymd: "2026-10-10", method: "archery", origin: null, includeUnknown: false });
    const best = bestPerProperty(out.ranked);
    expect(best.map((r) => r.unit.id)).toEqual(["bigopen", "open"]);
    expect(best[0].more).toBe(2);
    expect(best[1].more).toBe(0);
  });

  it("scores travel time", () => {
    expect(travelScore(10)).toBe(100);
    expect(travelScore(200)).toBe(0);
    expect(travelScore(null)).toBeNull();
  });
});
