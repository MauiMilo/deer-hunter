"use client";

import { useEffect, useMemo, useState } from "react";
import { hoursInWindow, scoreConditions, windowBounds, type ConditionsResult, type Window } from "@/lib/conditions";
import { legalHours } from "@/lib/sun";
import type { Regulations } from "@/lib/types";
import { cellKey, fetchForecasts, type ForecastResult, type PointForecast } from "@/lib/weather";

/** Seven-day forecasts for every 0.2-degree cell that contains at least one of the given points. */
export function useForecast(points: [number, number][]) {
  const cells = useMemo(() => {
    const m = new Map<string, { lat: number; lon: number }>();
    for (const [lon, lat] of points) {
      const k = cellKey(lon, lat);
      if (!m.has(k)) {
        const [la, lo] = k.split(",").map(Number);
        m.set(k, { lat: la, lon: lo });
      }
    }
    return m;
  }, [points]);
  const sig = [...cells.keys()].sort().join("|");
  const [state, setState] = useState<{ loading: boolean; result: ForecastResult | null }>({ loading: false, result: null });

  useEffect(() => {
    if (!cells.size) return;
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState((s) => ({ ...s, loading: true }));
    fetchForecasts(cells).then((result) => alive && setState({ loading: false, result }));
    return () => {
      alive = false;
    };
    // `sig` captures the set of cells; re-fetch only when it changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig]);

  const byKey = useMemo(() => new Map((state.result?.points ?? []).map((p) => [p.key, p])), [state.result]);
  return { loading: state.loading, error: state.result?.error ?? null, fetchedAt: state.result?.fetchedAt ?? null, byKey };
}

export function forecastFor(byKey: Map<string, PointForecast>, point: [number, number]): PointForecast | undefined {
  return byKey.get(cellKey(point[0], point[1]));
}

export function conditionsAt(
  fc: PointForecast | undefined,
  point: [number, number],
  ymd: string,
  window: Window,
  regs: Regulations,
): { conditions: ConditionsResult | null; legal: ReturnType<typeof legalHours> } {
  const legal = legalHours(ymd, point[1], point[0], regs.legal_hours.before_sunrise_min, regs.legal_hours.after_sunset_min);
  if (!fc || !legal) return { conditions: null, legal };
  const hours = hoursInWindow(fc.hours, windowBounds(window, legal.start, legal.end));
  return { conditions: scoreConditions(hours), legal };
}
