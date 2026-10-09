// Test-only fixtures. These never ship in the app's data.
import type { Catalog, Property, Regulations, Unit } from "../types";

export const regs: Regulations = {
  season_year: "2026-27",
  verified_against_print: false,
  sources: {},
  legal_hours: { rule: "", before_sunrise_min: 30, after_sunset_min: 30, source: "regulations" },
  seasons: [
    { method: "archery", units: ["A"], start: "2026-09-15", end: "2026-12-08", deer: "any" },
    { method: "archery", units: ["B"], start: "2026-09-15", end: "2026-12-15", deer: "any" },
    { method: "muzzleloader", units: ["A", "B"], start: "2026-10-31", end: "2026-11-10", deer: "antlered" },
    { method: "firearm", units: ["A"], start: "2026-11-11", end: "2026-11-11", deer: "any" },
    { method: "firearm", units: ["A"], start: "2026-11-12", end: "2026-11-29", deer: "antlered" },
    { method: "firearm", units: ["B"], start: "2026-11-11", end: "2026-11-11", deer: "any" },
    { method: "firearm", units: ["B"], start: "2026-11-12", end: "2026-12-06", deer: "antlered" },
  ],
  definitions: { any: "", antlered: "" },
  method_notes: {},
};

export function unit(id: string, propertyId: string, score: number | null, point: [number, number], units = ["A"]): Unit {
  return {
    id,
    property_id: propertyId,
    label: null,
    is_block: false,
    acres: 500,
    point,
    bbox: [point[0], point[1], point[0], point[1]],
    town: "Pittsburg",
    wmu: { units, confidence: units.length > 1 ? "split-town" : "town-wide", note: "" },
    score: {
      score,
      coverage: 0.15,
      provisional: true,
      confidence: "low",
      summary: "",
      factors: [
        { key: "habitat", label: "", value: null, weight: 0.35, confidence: "none", basis: "missing", basis_label: "", evidence: [], signals: {} },
        { key: "access", label: "", value: score, weight: 0.15, confidence: "low", basis: "heuristic", basis_label: "", evidence: [], signals: {} },
      ],
    },
  };
}

export function property(id: string, status: Property["access"]["status"]): Property {
  return {
    id,
    name: id,
    tract_ids: [],
    tract_names: [],
    parent_id: null,
    alt_name: null,
    parent_name: null,
    protection_type: null,
    agency: null,
    secondary_agency: null,
    agency_type: null,
    owner_type: "State",
    public_access: "",
    management_status: "",
    program: null,
    boundary_accuracy: "",
    boundary_accuracy_code: 2,
    reported_acres: null,
    parent_acres: null,
    date_altered: null,
    notes: null,
    acres: 500,
    clipped_to_region: false,
    towns: [],
    wmu_units: ["A"],
    access: { status, rule_id: "x", summary: "", restrictions: [], sources: [], checked_on: null, notes: [] },
    overlaps: [],
    point: [-71.4, 45.05],
    bbox: [-71.4, 45.05, -71.4, 45.05],
    unit_ids: [],
    best_unit_score: null,
  };
}

export function catalog(units: Unit[], props: Property[]): Catalog {
  return {
    generated_at: "2026-10-08T00:00:00Z",
    region: { slug: "coos", name: "Coos County, NH", focus_towns: [] },
    general_restrictions: [],
    scoring: { weights: { habitat: 0.35, pressure: 0.2, terrain: 0.2, access: 0.15, abundance: 0.1 }, provisional_below_coverage: 0.5 },
    properties: props,
    units,
  };
}
