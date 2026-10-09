"use client";

import { useCallback, useEffect, useState } from "react";
import type { Window } from "@/lib/conditions";
import { DEFAULT_TRIP_WEIGHTS, type TripWeights } from "@/lib/rank";
import { load, save } from "@/lib/storage";
import type { FactorKey, Method } from "@/lib/types";

export interface Settings {
  method: Method;
  window: Window;
  includeUnknown: boolean;
  /** Where to measure distance from when GPS isn't used. */
  home: { label: string; lon: number; lat: number };
  factorWeights: Record<FactorKey, number> | null; // null = use the pipeline's weights
  tripWeights: TripWeights;
}

// Pittsburg village (approximate town center) is the default starting point.
export const DEFAULT_HOME = { label: "Pittsburg village", lon: -71.3912, lat: 45.0515 };

export const DEFAULT_SETTINGS: Settings = {
  method: "archery",
  window: "morning",
  includeUnknown: false,
  home: DEFAULT_HOME,
  factorWeights: null,
  tripWeights: DEFAULT_TRIP_WEIGHTS,
};

const KEY = "ds.settings.v1";
const EVENT = "ds-settings";

export function useSettings(): [Settings, (patch: Partial<Settings>) => void, boolean] {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // Read once after mount (browser storage isn't available while the page is prerendered).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSettings(load(KEY, DEFAULT_SETTINGS));
    setReady(true);
    const onChange = () => setSettings(load(KEY, DEFAULT_SETTINGS));
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    const next = { ...load(KEY, DEFAULT_SETTINGS), ...patch };
    save(KEY, next);
    setSettings(next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return [settings, update, ready];
}
