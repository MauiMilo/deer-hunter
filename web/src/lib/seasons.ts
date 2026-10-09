import type { Method, Regulations, Season } from "./types";

export const METHOD_LABELS: Record<Method, string> = {
  archery: "Archery",
  muzzleloader: "Muzzleloader",
  firearm: "Firearm",
  youth: "Youth weekend",
};

export interface SeasonStatus {
  open: boolean;
  deer: "any" | "antlered" | null;
  /** Units the answer was checked against. */
  units: string[];
  certainty: "known-unit" | "split-unit" | "unknown-unit";
  message: string;
  seasons: Season[];
}

function inRange(ymd: string, s: Season): boolean {
  return s.start <= ymd && ymd <= s.end;
}

function forUnit(regs: Regulations, ymd: string, method: Method, unit: string): Season | null {
  return regs.seasons.find((s) => s.method === method && s.units.includes(unit) && inRange(ymd, s)) ?? null;
}

/**
 * Is `method` open on `ymd` for a spot whose WMU might be any of `units`?
 * When the spot could be in more than one unit (a town split by a boundary road), the season
 * counts as open only if it's open in every candidate unit, and the stricter deer rule wins.
 */
export function seasonStatus(regs: Regulations, ymd: string, method: Method, units: string[]): SeasonStatus {
  if (!units.length) {
    return {
      open: false,
      deer: null,
      units,
      certainty: "unknown-unit",
      message: "Wildlife Management Unit not known here; check the digest map.",
      seasons: [],
    };
  }
  const hits = units.map((u) => forUnit(regs, ymd, method, u));
  const certainty = units.length > 1 ? "split-unit" : "known-unit";
  if (hits.some((h) => h === null)) {
    const openSome = hits.some((h) => h !== null);
    return {
      open: false,
      deer: null,
      units,
      certainty,
      message: openSome
        ? `Open in only some of WMU ${units.join("/")} on this date. Check which side of the boundary you're on.`
        : `${METHOD_LABELS[method]} season is closed in WMU ${units.join("/")} on this date.`,
      seasons: hits.filter((h): h is Season => h !== null),
    };
  }
  const seasons = hits as Season[];
  const deer = seasons.some((s) => s.deer === "antlered") ? "antlered" : "any";
  return {
    open: true,
    deer,
    units,
    certainty,
    message: `${METHOD_LABELS[method]} open in WMU ${units.join("/")}: ${deer === "any" ? "any deer" : "antlered deer only"}.`,
    seasons,
  };
}

/** Next date on/after `ymd` when `method` opens in all of `units`, if any this season. */
export function nextOpening(regs: Regulations, ymd: string, method: Method, units: string[]): string | null {
  const starts = regs.seasons
    .filter((s) => s.method === method && units.every((u) => regs.seasons.some((x) => x.method === method && x.units.includes(u))))
    .map((s) => s.start)
    .filter((d) => d > ymd)
    .sort();
  for (const d of starts) if (seasonStatus(regs, d, method, units).open) return d;
  return null;
}
