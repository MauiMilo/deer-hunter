"use client";

import { useCallback, useEffect, useState } from "react";
import type { Observation, Waypoint } from "@/lib/fieldlog";
import { loadList, save } from "@/lib/storage";

const WP_KEY = "ds.waypoints.v1";
const OBS_KEY = "ds.observations.v1";
const EVENT = "ds-fieldlog";

/** Waypoints and observations, stored only in this phone's browser. */
export function useFieldLog() {
  const [waypoints, setWaypoints] = useState<Waypoint[]>([]);
  const [observations, setObservations] = useState<Observation[]>([]);

  useEffect(() => {
    const read = () => {
      setWaypoints(loadList<Waypoint>(WP_KEY));
      setObservations(loadList<Observation>(OBS_KEY));
    };
    read();
    window.addEventListener(EVENT, read);
    return () => window.removeEventListener(EVENT, read);
  }, []);

  const commit = useCallback((key: string, list: unknown[]) => {
    const ok = save(key, list);
    window.dispatchEvent(new Event(EVENT));
    return ok;
  }, []);

  return {
    waypoints,
    observations,
    addWaypoint: (w: Waypoint) => commit(WP_KEY, [w, ...loadList<Waypoint>(WP_KEY)]),
    removeWaypoint: (id: string) => commit(WP_KEY, loadList<Waypoint>(WP_KEY).filter((w) => w.id !== id)),
    addObservation: (o: Observation) => commit(OBS_KEY, [o, ...loadList<Observation>(OBS_KEY)]),
    removeObservation: (id: string) => commit(OBS_KEY, loadList<Observation>(OBS_KEY).filter((o) => o.id !== id)),
  };
}
