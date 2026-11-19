"use client";

import { useCallback, useEffect, useState } from "react";
import type { Window } from "@/lib/conditions";
import { DEFAULT_TRIP_WEIGHTS, type TripWeights } from "@/lib/rank";
import type { Home } from "@/lib/regions";
import { load, save } from "@/lib/storage";
import type { FactorKey, Method } from "@/lib/types";

export interface Settings {
  method: Method;
  window: Window;
  includeUnknown: boolean;
  /** Which region's data to show (null = the default region). */
  region: string | null;
  /** Where to measure distance from when GPS isn't used, per region (see homeFor in lib/regions). */
  homes: Record<string, Home>;
  /** Coos starting point saved before regions existed; still used for Coos if no newer one is saved. */
  home: Home;
  factorWeights: Record<FactorKey, number> | null; // null = use the pipeline's weights
  tripWeights: TripWeights;
}

// Pittsburg village (approximate town center) is the default Coos starting point.
export const DEFAULT_HOME = { label: "Pittsburg village", lon: -71.3912, lat: 45.0515 };

export const DEFAULT_SETTINGS: Settings = {
  method: "archery",
  window: "morning",
  includeUnknown: false,
  region: null,
  homes: {},
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
