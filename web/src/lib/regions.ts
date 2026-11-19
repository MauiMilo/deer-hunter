// Regions: each one's data lives in its own folder (public/data/<slug>/), listed in
// public/data/regions.json (written by the pipeline from config.py). You pick one in Settings;
// the app shows one region at a time and remembers a starting point for each.

export interface Home {
  label: string;
  lon: number;
  lat: number;
}

export interface RegionInfo {
  slug: string;
  name: string;
  short_name: string;
  /** Folder the region's files are served from, e.g. "/data/coos/". */
  path: string;
  /** Where the map opens (lon, lat). */
  center: [number, number];
  bbox: [number, number, number, number];
  /** Default starting point for distances. */
  home: Home;
}

export interface RegionIndex {
  default: string;
  regions: RegionInfo[];
}

export const REGIONS_URL = "/data/regions.json";

/** Used only if regions.json can't be read: Coos, as the app has always shown it. */
export const FALLBACK_INDEX: RegionIndex = {
  default: "coos",
  regions: [
    {
      slug: "coos",
      name: "Coos County, NH",
      short_name: "Coos",
      path: "/data/coos/",
      center: [-71.3, 45.05],
      bbox: [-71.85, 44.2, -70.95, 45.31],
      home: { label: "Pittsburg village", lon: -71.3912, lat: 45.0515 },
    },
  ],
};

/** Saved places, settings and logs from before regions existed all belong to Coos. */
export const LEGACY_REGION = "coos";

/** The region to show: the one you picked if it still exists, otherwise the default. */
export function pickRegion(index: RegionIndex, wanted: string | null | undefined): RegionInfo {
  const byslug = (s: string | null | undefined) => (s ? index.regions.find((r) => r.slug === s) : undefined);
  const r = byslug(wanted) ?? byslug(index.default) ?? index.regions[0];
  if (!r) throw new Error("regions.json lists no regions");
  return r;
}

/** URL of one of a region's data files. */
export function dataUrl(region: Pick<RegionInfo, "path">, file: string): string {
  return region.path.replace(/\/?$/, "/") + file.replace(/^\//, "");
}

/** Check a parsed regions.json before trusting it. */
export function isRegionIndex(v: unknown): v is RegionIndex {
  if (!v || typeof v !== "object") return false;
  const o = v as RegionIndex;
  return (
    typeof o.default === "string" &&
    Array.isArray(o.regions) &&
    o.regions.length > 0 &&
    o.regions.every((r) => typeof r.slug === "string" && typeof r.path === "string" && Array.isArray(r.center) && !!r.home)
  );
}

export interface HomeSettings {
  /** Starting point you saved for each region. */
  homes?: Record<string, Home>;
  /** Starting point from before regions existed (Coos). */
  home?: Home;
}

/**
 * Where distances are measured from in a region: the spot you saved for that region, else
 * (for Coos only) the starting point saved before regions existed, else the region's default.
 */
export function homeFor(settings: HomeSettings, region: RegionInfo): Home {
  const saved = settings.homes?.[region.slug];
  if (saved) return saved;
  if (region.slug === LEGACY_REGION && settings.home) return settings.home;
  return region.home;
}

/** The region a saved place belongs to (places saved before regions existed are Coos). */
export function regionOf(item: { region?: string }): string {
  return item.region || LEGACY_REGION;
}
