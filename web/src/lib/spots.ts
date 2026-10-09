// Scouting spots checked against a day's wind.

import type { Spot } from "./types";
import { approachFit, compass, type Fit } from "./wind";

export interface SpotEval {
  spot: Spot;
  windFit: Fit | null;
  approachFit: Fit | null;
  /** Heading to walk from the nearest road to the spot. */
  approachBearing: number | null;
  dayScore: number;
  notes: string[];
}

const WIND_PENALTY: Record<Fit, number> = { good: 0, marginal: 10, bad: 25 };

export function approachBearing(spot: Spot): number | null {
  return spot.approach ? (spot.approach.road_bearing_deg + 180) % 360 : null;
}

function inArc(deg: number, [a, b]: [number, number]): boolean {
  const d = ((deg % 360) + 360) % 360;
  return a <= b ? d >= a && d <= b : d >= a || d <= b;
}

export function spotFitFromArcs(windFromDeg: number, spot: Spot): Fit {
  if (spot.good_winds_from.some((arc) => inArc(windFromDeg, arc))) return "good";
  // within 20 degrees of a good arc counts as marginal
  if (spot.good_winds_from.some(([a, b]) => inArc(windFromDeg, [(a + 340) % 360, (b + 20) % 360]))) return "marginal";
  return "bad";
}

export function evaluateSpot(spot: Spot, windFromDeg: number | null): SpotEval {
  const ab = approachBearing(spot);
  if (windFromDeg === null) {
    return { spot, windFit: null, approachFit: null, approachBearing: ab, dayScore: spot.score, notes: ["No forecast wind to check against."] };
  }
  const wf = spotFitFromArcs(windFromDeg, spot);
  const af = ab === null ? null : approachFit(windFromDeg, ab);
  const notes: string[] = [];
  if (wf === "good") notes.push("Today's wind blows across the likely travel route, carrying your scent off it.");
  if (wf === "marginal") notes.push("Today's wind is partly along the travel route; scent may drift onto it.");
  if (wf === "bad") notes.push("Today's wind blows along the travel route: your scent would run straight down it.");
  if (af === "bad") notes.push(`Walking in from the road (heading ${compass(ab!)}), the wind would be at your back.`);
  if (af === "good") notes.push(`The walk in from the road (heading ${compass(ab!)}) is into the wind.`);
  const dayScore = Math.max(0, spot.score - WIND_PENALTY[wf] - (af === "bad" ? 10 : 0));
  return { spot, windFit: wf, approachFit: af, approachBearing: ab, dayScore, notes };
}

export function bestSpot(spots: Spot[], windFromDeg: number | null): SpotEval | null {
  let best: SpotEval | null = null;
  for (const s of spots) {
    const e = evaluateSpot(s, windFromDeg);
    if (!best || e.dayScore > best.dayScore) best = e;
  }
  return best;
}

export const FIT_TEXT: Record<Fit, string> = { good: "Wind works", marginal: "Wind so-so", bad: "Wrong wind" };
