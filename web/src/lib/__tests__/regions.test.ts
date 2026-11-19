import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { dataUrl, FALLBACK_INDEX, homeFor, isRegionIndex, pickRegion, regionOf, type RegionIndex } from "../regions";

const PUBLIC = join(__dirname, "../../../public");
const real = JSON.parse(readFileSync(join(PUBLIC, "data/regions.json"), "utf8")) as RegionIndex;

const index: RegionIndex = {
  default: "coos",
  regions: [
    FALLBACK_INDEX.regions[0],
    {
      slug: "concord",
      name: "Concord area",
      short_name: "Concord area",
      path: "/data/concord/",
      center: [-71.5381, 43.2067],
      bbox: [-72.19, 42.75, -70.88, 43.71],
      home: { label: "Concord (State House)", lon: -71.5381, lat: 43.2067 },
    },
  ],
};

describe("regions.json", () => {
  it("is valid and lists Coos as the default", () => {
    expect(isRegionIndex(real)).toBe(true);
    expect(real.default).toBe("coos");
    expect(real.regions.map((r) => r.slug)).toContain("concord");
  });

  it("gives every region its own folder", () => {
    const paths = real.regions.map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const r of real.regions) expect(r.path).toBe(`/data/${r.slug}/`);
  });

  it("matches the built-in Coos fallback, so Coos looks the same either way", () => {
    expect(real.regions.find((r) => r.slug === "coos")).toEqual(FALLBACK_INDEX.regions[0]);
  });

  it("has the Coos data files in the Coos folder", () => {
    for (const f of ["catalog.json", "regulations.json", "manifest.json", "properties.geojson", "blocks.geojson", "spots.geojson"]) {
      expect(existsSync(join(PUBLIC, "data/coos", f)), f).toBe(true);
      expect(existsSync(join(PUBLIC, "data", f)), `old top-level ${f}`).toBe(false);
    }
  });

  it("rejects malformed lists", () => {
    expect(isRegionIndex(null)).toBe(false);
    expect(isRegionIndex({ default: "coos", regions: [] })).toBe(false);
    expect(isRegionIndex({ default: "coos", regions: [{ slug: "x" }] })).toBe(false);
  });
});

describe("pickRegion", () => {
  it("uses the region you picked", () => {
    expect(pickRegion(index, "concord").slug).toBe("concord");
  });
  it("falls back to the default when nothing is picked or the pick no longer exists", () => {
    expect(pickRegion(index, null).slug).toBe("coos");
    expect(pickRegion(index, "grafton").slug).toBe("coos");
  });
  it("falls back to the first region if the default is missing", () => {
    expect(pickRegion({ ...index, default: "gone" }, undefined).slug).toBe("coos");
  });
});

describe("dataUrl", () => {
  it("joins folder and file", () => {
    expect(dataUrl({ path: "/data/concord/" }, "catalog.json")).toBe("/data/concord/catalog.json");
    expect(dataUrl({ path: "/data/concord" }, "/spots.geojson")).toBe("/data/concord/spots.geojson");
  });
});

describe("homeFor", () => {
  const [coos, concord] = index.regions;
  it("uses each region's default when nothing is saved", () => {
    expect(homeFor({}, concord).label).toBe("Concord (State House)");
    expect(homeFor({}, coos).label).toBe("Pittsburg village");
  });
  it("keeps a starting point saved before regions existed, for Coos only", () => {
    const old = { home: { label: "Saved spot", lon: -71.2, lat: 45.1 } };
    expect(homeFor(old, coos)).toEqual(old.home);
    expect(homeFor(old, concord).label).toBe("Concord (State House)");
  });
  it("remembers a separate starting point per region", () => {
    const s = { homes: { concord: { label: "Camp", lon: -71.7, lat: 43.1 } }, home: { label: "Saved spot", lon: -71.2, lat: 45.1 } };
    expect(homeFor(s, concord).label).toBe("Camp");
    expect(homeFor(s, coos).label).toBe("Saved spot");
  });
});

describe("regionOf", () => {
  it("treats places saved before regions existed as Coos", () => {
    expect(regionOf({})).toBe("coos");
    expect(regionOf({ region: "concord" })).toBe("concord");
  });
});
