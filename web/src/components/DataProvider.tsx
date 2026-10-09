"use client";

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Catalog, Manifest, Property, Regulations, Unit } from "@/lib/types";

interface DataState {
  loading: boolean;
  error: string | null;
  catalog: Catalog | null;
  regs: Regulations | null;
  manifest: Manifest | null;
  propertyById: Map<string, Property>;
  unitById: Map<string, Unit>;
}

const Ctx = createContext<DataState | null>(null);

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export function DataProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Omit<DataState, "propertyById" | "unitById">>({
    loading: true,
    error: null,
    catalog: null,
    regs: null,
    manifest: null,
  });

  useEffect(() => {
    let alive = true;
    Promise.all([
      getJson<Catalog>("/data/catalog.json"),
      getJson<Regulations>("/data/regulations.json"),
      getJson<Manifest>("/data/manifest.json"),
    ])
      .then(([catalog, regs, manifest]) => alive && setState({ loading: false, error: null, catalog, regs, manifest }))
      .catch((e: Error) =>
        alive &&
        setState({
          loading: false,
          error: `The property data hasn't been built yet or couldn't load (${e.message}).`,
          catalog: null,
          regs: null,
          manifest: null,
        }),
      );
    return () => {
      alive = false;
    };
  }, []);

  const value = useMemo<DataState>(
    () => ({
      ...state,
      propertyById: new Map((state.catalog?.properties ?? []).map((p) => [p.id, p])),
      unitById: new Map((state.catalog?.units ?? []).map((u) => [u.id, u])),
    }),
    [state],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useData(): DataState {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData outside DataProvider");
  return v;
}
