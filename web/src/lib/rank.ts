// "Where should I go?" ranking for a chosen date, time window and method.
//
// Legal status is a gate, not a score: prohibited land never appears, and land with unknown
// permission only appears when you ask for research candidates. Within what's left, units are
// ordered by a trip score that blends property quality, the day's conditions and travel.

import type { ConditionsResult } from "./conditions";
import { haversineMiles, roughDriveMinutes } from "./geo";
import { seasonStatus, type SeasonStatus } from "./seasons";
import type { Catalog, Method, Property, Regulations, Unit } from "./types";

export interface TripWeights {
  quality: number;
  conditions: number;
  travel: number;
}

export const DEFAULT_TRIP_WEIGHTS: TripWeights = { quality: 0.65, conditions: 0.2, travel: 0.15 };

export interface RankInput {
  catalog: Catalog;
  regs: Regulations;
  ymd: string;
  method: Method;
  origin: [number, number] | null;
  includeUnknown: boolean;
  conditionsFor?: (u: Unit) => ConditionsResult | null;
  weights?: TripWeights;
  factorWeights?: Record<string, number>;
}

export interface Ranked {
  unit: Unit;
  property: Property;
  season: SeasonStatus;
  quality: number | null;
  conditions: ConditionsResult | null;
  miles: number | null;
  driveMin: number | null;
  travel: number | null;
  trip: number;
  parts: { label: string; value: number; weight: number }[];
}

export interface RankOutput {
  ranked: Ranked[];
  excluded: { prohibited: number; unknown: number; closed: number };
}

/** Recompute a unit's quality score with custom factor weights (from Settings). */
export function reweight(unit: Unit, weights?: Record<string, number>): number | null {
  if (!weights) return unit.score.score;
  let num = 0, den = 0;
  for (const f of unit.score.factors) {
    const w = weights[f.key] ?? f.weight;
    if (f.value !== null && w > 0) {
      num += f.value * w;
      den += w;
    }
  }
  return den > 0 ? num / den : null;
}

export function travelScore(driveMin: number | null): number | null {
  if (driveMin === null) return null;
  // 100 at 15 minutes or less, 0 at 150 minutes or more.
  return Math.max(0, Math.min(100, ((150 - driveMin) / 135) * 100));
}

export function rank(input: RankInput): RankOutput {
  const w = input.weights ?? DEFAULT_TRIP_WEIGHTS;
  const props = new Map(input.catalog.properties.map((p) => [p.id, p]));
  const excluded = { prohibited: 0, unknown: 0, closed: 0 };
  const ranked: Ranked[] = [];

  for (const unit of input.catalog.units) {
    const property = props.get(unit.property_id);
    if (!property) continue;
    const status = property.access.status;
    if (status === "prohibited") {
      excluded.prohibited++;
      continue;
    }
    if (status === "unknown" && !input.includeUnknown) {
      excluded.unknown++;
      continue;
    }
    const season = seasonStatus(input.regs, input.ymd, input.method, unit.wmu.units);
    if (!season.open) {
      excluded.closed++;
      continue;
    }
    const quality = reweight(unit, input.factorWeights);
    const conditions = input.conditionsFor?.(unit) ?? null;
    const miles = input.origin ? haversineMiles(input.origin, unit.point) : null;
    const driveMin = miles === null ? null : roughDriveMinutes(miles);
    const travel = travelScore(driveMin);

    const parts: Ranked["parts"] = [];
    if (quality !== null) parts.push({ label: "Property quality", value: quality, weight: w.quality });
    if (conditions) parts.push({ label: "Day's conditions", value: conditions.score, weight: w.conditions });
    if (travel !== null) parts.push({ label: "Travel", value: travel, weight: w.travel });
    const den = parts.reduce((a, p) => a + p.weight, 0);
    const trip = den > 0 ? parts.reduce((a, p) => a + p.value * p.weight, 0) / den : 0;

    ranked.push({ unit, property, season, quality, conditions, miles, driveMin, travel, trip, parts });
  }

  ranked.sort((a, b) => {
    // Verified land always ahead of research candidates, then by trip score.
    const av = a.property.access.status === "verified" ? 0 : 1;
    const bv = b.property.access.status === "verified" ? 0 : 1;
    return av - bv || b.trip - a.trip || (a.miles ?? 0) - (b.miles ?? 0);
  });
  return { ranked, excluded };
}
