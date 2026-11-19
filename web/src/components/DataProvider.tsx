"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useSettings } from "@/components/useSettings";
import { dataUrl, FALLBACK_INDEX, isRegionIndex, pickRegion, REGIONS_URL, type RegionIndex, type RegionInfo } from "@/lib/regions";
import type { Catalog, LandcoverMeta, Manifest, Property, Regulations, Spot, Unit, WindHistory, ParkingArea } from "@/lib/types";

interface DataState {
  /** Every region the app can show, and the one being shown. */
  regions: RegionInfo[];
  region: RegionInfo;
  /** URL of one of the shown region's data files. */
  fileUrl: (file: string) => string;
  /** Show another region (remembered on this phone). */
  setRegion: (slug: string) => void;
  loading: boolean;
  error: string | null;
  catalog: Catalog | null;
  regs: Regulations | null;
  manifest: Manifest | null;
  windHistory: WindHistory | null;
  landcover: LandcoverMeta | null;
  /** Parking areas confirmed on the ground (data/parking.yaml). */
  parking: ParkingArea[];
  /** Areas inside properties where only some methods are allowed (zones.geojson), drawn on the map. */
  zones: ZoneCollection | null;
  propertyById: Map<string, Property>;
  unitById: Map<string, Unit>;
  spotById: Map<string, Spot>;
}

export interface ZoneCollection {
  type: "FeatureCollection";
  features: { type: "Feature"; geometry: unknown; properties: { id: string; name: string; methods: string[]; approximate: boolean } }[];
}

const Ctx = createContext<DataState | null>(null);

async function optionalJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(path, { cache: "no-cache" });
    return res.ok ? ((await res.json()) as T) : null;
  } catch {
    return null;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

type FileState = Omit<DataState, "propertyById" | "unitById" | "spotById" | "regions" | "region" | "fileUrl" | "setRegion">;

export function DataProvider({ children }: { children: ReactNode }) {
  const [settings, updateSettings, settingsReady] = useSettings();
  const [index, setIndex] = useState<RegionIndex | null>(null);
  const region = pickRegion(index ?? FALLBACK_INDEX, settings.region);
  const [state, setState] = useState<FileState>({
    loading: true,
    error: null,
    catalog: null,
    regs: null,
    manifest: null,
    windHistory: null,
    landcover: null,
    parking: [],
    zones: null,
  });

  // The list of regions (falls back to Coos alone if it can't be read).
  useEffect(() => {
    let alive = true;
    optionalJson<unknown>(REGIONS_URL).then((v) => alive && setIndex(isRegionIndex(v) ? v : FALLBACK_INDEX));
    return () => {
      alive = false;
    };
  }, []);

  // The shown region's files. Waits for the list and your saved choice so it loads once.
  const ready = index !== null && settingsReady;
  const path = region.path;
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    const at = (f: string) => dataUrl({ path }, f);
    // Clear the previous region's data so no screen mixes two regions while the new one loads.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ loading: true, error: null, catalog: null, regs: null, manifest: null, windHistory: null, landcover: null, parking: [], zones: null });
    Promise.all([
      getJson<Catalog>(at("catalog.json")),
      getJson<Regulations>(at("regulations.json")),
      getJson<Manifest>(at("manifest.json")),
      optionalJson<WindHistory>(at("wind_history.json")),
      optionalJson<LandcoverMeta>(at("landcover.json")),
      optionalJson<{ features: { geometry: { coordinates: [number, number] }; properties: Omit<ParkingArea, "point"> }[] }>(at("parking.geojson")),
      optionalJson<ZoneCollection>(at("zones.geojson")),
    ])
      .then(
        ([catalog, regs, manifest, windHistory, landcover, parkingFc, zones]) =>
          alive &&
          setState({
            loading: false,
            error: null,
            catalog,
            regs,
            manifest,
            windHistory,
            landcover,
            parking: (parkingFc?.features ?? []).map((f) => ({ ...f.properties, point: f.geometry.coordinates })),
            zones: zones?.features?.length ? zones : null,
          }),
      )
      .catch((e: Error) =>
        alive &&
        setState({
          loading: false,
          error: `The data for this region hasn't been built yet or couldn't load (${e.message}).`,
          catalog: null,
          regs: null,
          manifest: null,
          windHistory: null,
          landcover: null,
          parking: [],
          zones: null,
        }),
      );
    return () => {
      alive = false;
    };
  }, [ready, path]);

  const setRegion = useCallback((slug: string) => updateSettings({ region: slug }), [updateSettings]);
  const regions = (index ?? FALLBACK_INDEX).regions;
  const fileUrl = useCallback((f: string) => dataUrl({ path }, f), [path]);

  const value = useMemo<DataState>(
    () => ({
      ...state,
      // Until the shown region's files have loaded, report loading (not the previous region's data).
      loading: state.loading || !ready,
      regions,
      region,
      fileUrl,
      setRegion,
      propertyById: new Map((state.catalog?.properties ?? []).map((p) => [p.id, p])),
      unitById: new Map((state.catalog?.units ?? []).map((u) => [u.id, u])),
      spotById: new Map((state.catalog?.spots ?? []).map((s) => [s.id, s])),
    }),
    [state, ready, regions, region, fileUrl, setRegion],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData outside DataProvider");
  return v;
}
