// Shapes of the data files the pipeline writes to /public/data.

export type AccessStatus = "verified" | "prohibited" | "unknown";

export interface SourceRef {
  id: string;
  title: string | null;
  url: string | null;
  publisher: string | null;
  source_date: string | null;
  retrieved: string | null;
}

export interface Access {
  status: AccessStatus;
  rule_id: string;
  summary: string;
  restrictions: string[];
  sources: SourceRef[];
  checked_on: string | null;
  notes: string[];
}

export type FactorKey = "habitat" | "pressure" | "terrain" | "access" | "abundance";

export interface Factor {
  key: FactorKey;
  label: string;
  value: number | null;
  weight: number;
  confidence: "none" | "low" | "medium" | "high";
  basis: "fact" | "supported" | "heuristic" | "assumption" | "missing";
  basis_label: string;
  evidence: string[];
  signals: Record<string, unknown>;
}

export interface Score {
  score: number | null;
  coverage: number;
  provisional: boolean;
  confidence: "none" | "low" | "medium" | "high";
  factors: Factor[];
  summary: string;
}

export interface Wmu {
  units: string[];
  confidence: "mapped" | "split-mapped" | "town-wide" | "split-town" | "unknown";
  note: string;
}

export interface Spot {
  id: string;
  unit_id: string;
  property_id: string;
  kind: "saddle" | "bench";
  point: [number, number];
  elevation_ft: number;
  slope_deg: number;
  score: number;
  confidence: "low" | "medium" | "high";
  reasons: string[];
  /** Likely direction deer travel through/along the feature, 0-180 degrees. */
  travel_axis_deg: number;
  good_winds_from: [number, number][];
  approach: { road_name: string | null; distance_m: number; road_bearing_deg: number } | null;
}

export interface Unit {
  id: string;
  property_id: string;
  label: string | null;
  is_block: boolean;
  acres: number;
  point: [number, number];
  bbox: [number, number, number, number];
  town: string | null;
  wmu: Wmu;
  score: Score;
  spot_ids?: string[];
}

export interface Property {
  id: string;
  name: string;
  tract_ids: string[];
  tract_names: string[];
  parent_id: string | null;
  alt_name: string | null;
  parent_name: string | null;
  protection_type: string | null;
  agency: string | null;
  secondary_agency: string | null;
  agency_type: string | null;
  owner_type: string;
  public_access: string;
  management_status: string;
  program: string | null;
  boundary_accuracy: string;
  boundary_accuracy_code: number | null;
  reported_acres: number | null;
  parent_acres: number | null;
  date_altered: string | null;
  notes: string | null;
  acres: number;
  clipped_to_region: boolean;
  towns: string[];
  wmu_units: string[];
  access: Access;
  overlaps: { id: string; name: string; shared_acres: number }[];
  point: [number, number];
  bbox: [number, number, number, number];
  unit_ids: string[];
  best_unit_score: number | null;
}

export interface Catalog {
  generated_at: string;
  region: { slug: string; name: string; focus_towns: string[] };
  general_restrictions: { text: string; sources: SourceRef[] }[];
  scoring: { weights: Record<FactorKey, number>; provisional_below_coverage: number };
  properties: Property[];
  units: Unit[];
  spots?: Spot[];
}

export type Method = "archery" | "muzzleloader" | "firearm" | "youth";

export interface Season {
  method: Method;
  units: string[];
  start: string;
  end: string;
  deer: "any" | "antlered";
  note?: string;
}

export interface Regulations {
  season_year: string;
  verified_against_print: boolean;
  sources: Record<string, { title: string; url: string; publisher: string; source_date?: string; retrieved: string }>;
  legal_hours: { rule: string; before_sunrise_min: number; after_sunset_min: number; source: string };
  seasons: Season[];
  definitions: Record<string, string>;
  method_notes: Record<string, string>;
}

export interface ManifestSource {
  name: string;
  status: "ok" | "failed" | "skipped";
  url?: string;
  retrieved_at?: string;
  features?: number;
  expected?: number | null;
  warnings?: string[];
  error?: string;
  data_published?: string;
}

export interface Manifest {
  pipeline_version: string;
  region: { slug: string; name: string; focus_towns: string[] };
  started_at: string;
  finished_at: string;
  sources: ManifestSource[];
  warnings: string[];
  limitations: string[];
  counts: {
    tracts: number;
    properties: number;
    units: number;
    blocks: number;
    access_status: Partial<Record<AccessStatus, number>>;
    total_acres: number;
  };
}

export interface WindRoseCell {
  hours: number;
  calm_share: number | null;
  sector_share: number[]; // N, NE, E, SE, S, SW, W, NW
  mean_from_deg: number | null;
  steadiness: number;
  median_mph: number | null;
  p90_mph: number | null;
}

export interface WindHistory {
  period: [string, string];
  note: string;
  cell_step_deg: number;
  points: Record<string, { lat: number; lon: number; elevation_m: number | null; seasons: Record<string, Partial<Record<"morning" | "evening", WindRoseCell>>> }>;
}

export interface LandcoverMeta {
  product: string;
  year: number | null;
  coordinates: [[number, number], [number, number], [number, number], [number, number]];
  legend: { code: number; label: string; rgb: [number, number, number] }[];
}
