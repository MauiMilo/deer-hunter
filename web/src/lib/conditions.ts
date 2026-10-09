// Daily Hunting Conditions Score (0-100) for a time window.
//
// Deliberately conservative: weather adjusts the score modestly, and mainly for things that
// clearly make a sit worse or unsafe (strong wind, heavy rain, storms, extreme cold/heat).
// No moon-phase or barometric bonuses. This is NOT a probability of seeing deer.
// See RESEARCH.md for the reasoning behind each rule.

import type { Hour } from "./weather";
import { circularMean, circularSpreadDeg } from "./wind";

export type Window = "morning" | "evening" | "allday";

export interface ConditionsResult {
  score: number;
  hours: number;
  parts: { label: string; delta: number; why: string }[];
  safety: string[];
  wind: { fromDeg: number | null; avgMph: number; maxGustMph: number; spreadDeg: number; steady: boolean };
  tempRange: [number, number] | null;
  precipIn: number;
  codes: number[];
}

export function windowBounds(window: Window, legalStart: Date, legalEnd: Date): [number, number] {
  const s = legalStart.getTime();
  const e = legalEnd.getTime();
  const threeH = 3 * 3600000;
  if (window === "morning") return [s, Math.min(e, s + threeH)];
  if (window === "evening") return [Math.max(s, e - threeH), e];
  return [s, e];
}

export function hoursInWindow(hours: Hour[], [start, end]: [number, number]): Hour[] {
  // An hourly value describes the hour starting at t; include hours overlapping the window.
  return hours.filter((h) => h.t + 3600000 > start && h.t < end);
}

const nums = (xs: (number | null)[]) => xs.filter((x): x is number => x !== null);

export function scoreConditions(hours: Hour[]): ConditionsResult | null {
  if (!hours.length) return null;
  const wind = nums(hours.map((h) => h.windMph));
  const gusts = nums(hours.map((h) => h.gustMph));
  const temps = nums(hours.map((h) => h.tempF));
  const precip = nums(hours.map((h) => h.precipIn)).reduce((a, b) => a + b, 0);
  const codes = nums(hours.map((h) => h.code));
  const dirs = hours.filter((h) => h.windFromDeg !== null && h.windMph !== null);
  const circ = circularMean(dirs.map((h) => h.windFromDeg!), dirs.map((h) => Math.max(h.windMph!, 0.5)));
  const avgMph = wind.length ? wind.reduce((a, b) => a + b, 0) / wind.length : 0;
  const maxGust = gusts.length ? Math.max(...gusts) : 0;

  const parts: ConditionsResult["parts"] = [];
  const safety: string[] = [];
  const add = (label: string, delta: number, why: string) => parts.push({ label, delta, why });

  if (avgMph > 20) add("Strong wind", -30, "Sustained wind over 20 mph: hard to hear, see movement, or hold a scent plan.");
  else if (avgMph > 15) add("Windy", -15, "Sustained wind 15-20 mph makes scent and sound unpredictable.");
  else if (avgMph > 10) add("Breezy", -5, "Moderate wind; manageable with a good setup.");

  if (maxGust >= 35) {
    add("Dangerous gusts", -20, `Gusts to ${Math.round(maxGust)} mph.`);
    safety.push(`Gusts to ${Math.round(maxGust)} mph: risk of falling limbs and trees. Avoid tree stands.`);
  } else if (maxGust >= 28) {
    safety.push(`Gusts to ${Math.round(maxGust)} mph: be careful with tree stands and dead trees.`);
  }

  if (precip >= 0.5) add("Heavy rain", -30, `About ${precip.toFixed(2)} in of precipitation in this window.`);
  else if (precip >= 0.2) add("Steady rain", -15, `About ${precip.toFixed(2)} in of precipitation in this window.`);

  if (codes.some((c) => c >= 95)) {
    add("Thunderstorms", -40, "Thunderstorms forecast.");
    safety.push("Thunderstorms forecast: lightning risk on ridges and in open areas.");
  }
  if (codes.some((c) => c === 56 || c === 57 || c === 66 || c === 67)) safety.push("Freezing rain possible: icy roads and tree stands.");

  if (temps.length) {
    const lo = Math.min(...temps);
    const hi = Math.max(...temps);
    if (lo < 0) {
      add("Extreme cold", -10, `Low near ${Math.round(lo)}°F.`);
      safety.push(`Temperatures below 0°F: frostbite risk on a long sit.`);
    }
    if (hi > 72) add("Unseasonably warm", -10, `High near ${Math.round(hi)}°F; deer activity tends to drop in warm weather.`);
    else if (hi > 65) add("Warm", -5, `High near ${Math.round(hi)}°F; deer activity tends to drop above the low 60s.`);
  }

  const score = Math.max(0, Math.min(100, 100 + parts.reduce((a, p) => a + p.delta, 0)));
  const spread = circularSpreadDeg(circ.steadiness);
  return {
    score,
    hours: hours.length,
    parts,
    safety,
    wind: { fromDeg: circ.meanDeg, avgMph, maxGustMph: maxGust, spreadDeg: spread, steady: spread <= 45 },
    tempRange: temps.length ? [Math.min(...temps), Math.max(...temps)] : null,
    precipIn: precip,
    codes,
  };
}
