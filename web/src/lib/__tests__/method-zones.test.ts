import { describe, expect, it } from "vitest";
import { methodAllowed, rank } from "../rank";
import { nextOpeningAny } from "../seasons";
import type { Unit } from "../types";
import { catalog, property, regs, unit } from "./fixtures";

function bowOnly(u: Unit, share = 1): Unit {
  return {
    ...u,
    method_limit: {
      methods: ["archery"],
      zone_id: "bear-brook-archery-only",
      zone_name: "Bear Brook game refuge (east of Podunk Road): bow and arrow only",
      share,
      approximate: true,
      note: "",
      how_drawn: "",
      sources: [],
    },
  };
}

describe("bow-only zones (Bear Brook east of Podunk Road)", () => {
  const props = [property("bb", "verified")];
  const west = unit("bb~west", "bb", 70, [-71.38, 43.12], ["B"]);
  const east = bowOnly(unit("bb~east", "bb", 90, [-71.34, 43.12], ["B"]));
  const cat = catalog([west, east], props);

  it("knows which methods a block allows", () => {
    expect(methodAllowed(west, "firearm")).toBe(true);
    expect(methodAllowed(east, "archery")).toBe(true);
    expect(methodAllowed(east, "firearm")).toBe(false);
    expect(methodAllowed(east, "muzzleloader")).toBe(false);
    expect(methodAllowed(east, "youth")).toBe(false);
  });

  it("drops bow-only blocks from rifle picks and says why", () => {
    const out = rank({ catalog: cat, regs, ymd: "2026-11-20", method: "firearm", origin: null, includeUnknown: false });
    expect(out.ranked.map((r) => r.unit.id)).toEqual(["bb~west"]);
    expect(out.excluded.method).toBe(1);
  });

  it("keeps them for archery", () => {
    const out = rank({ catalog: cat, regs, ymd: "2026-11-20", method: "archery", origin: null, includeUnknown: false });
    expect(out.ranked.map((r) => r.unit.id).sort()).toEqual(["bb~east", "bb~west"]);
    expect(out.excluded.method).toBe(0);
  });

  it("treats a block only partly in the zone by the stricter rule", () => {
    const part = bowOnly(unit("bb~edge", "bb", 80, [-71.36, 43.12], ["B"]), 0.3);
    const out = rank({ catalog: catalog([part], props), regs, ymd: "2026-11-20", method: "firearm", origin: null, includeUnknown: false });
    expect(out.ranked).toHaveLength(0);
  });

  it("leaves Coos-style blocks (no zone) alone", () => {
    const out = rank({ catalog: catalog([unit("c", "c", 50, [-71.4, 45.05])], [property("c", "verified")]), regs, ymd: "2026-11-20", method: "firearm", origin: null, includeUnknown: false });
    expect(out.ranked).toHaveLength(1);
  });
});

describe("next opening across a region's WMUs", () => {
  it("reports the earliest unit to open, not just WMU A", () => {
    // After Dec 8 archery is closed in A but still open in B; firearm reopens nowhere.
    expect(nextOpeningAny(regs, "2026-09-01", "archery", ["A", "B"])).toEqual({ date: "2026-09-15", units: ["A", "B"] });
    expect(nextOpeningAny(regs, "2026-11-01", "firearm", ["B", "A", "B"])).toEqual({ date: "2026-11-11", units: ["A", "B"] });
    expect(nextOpeningAny(regs, "2026-12-20", "firearm", ["A", "B"])).toBeNull();
    expect(nextOpeningAny(regs, "2026-11-01", "firearm", [])).toBeNull();
  });
});

describe("deer abundance on the property screen", () => {
  it("reads the figure and its source from the block's score", async () => {
    const { abundanceInfo } = await import("../rank");
    const u = unit("x", "x", 50, [-71.6, 43.2], ["K"]);
    expect(abundanceInfo(u)).toBeNull(); // not loaded yet
    u.score.factors.push({
      key: "abundance",
      label: "Regional deer abundance",
      value: 80,
      weight: 0.1,
      confidence: "medium",
      basis: "fact",
      basis_label: "",
      evidence: [],
      signals: { buck_kill_per_sqmi: 2.06, where: "WMU K", year: 2025, source: { title: "2025 NH Wildlife Harvest Summary", url: "https://www.wildlife.nh.gov/x.pdf" } },
    });
    expect(abundanceInfo(u)).toEqual({
      buckKillPerSqMi: 2.06,
      where: "WMU K",
      year: 2025,
      source: { title: "2025 NH Wildlife Harvest Summary", url: "https://www.wildlife.nh.gov/x.pdf" },
    });
  });
});
