"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { MAX_FILE_BYTES, parseFile, type ImportedFeature } from "@/lib/importfile";
import { loadList, save } from "@/lib/storage";
import { newId } from "@/lib/fieldlog";

const KEY = "ds.imported.v1";
const EVENT = "ds-imported";

export interface ImportedLayer {
  id: string;
  name: string;
  importedAt: string;
  points: number;
  lines: number;
  areas: number;
  features: ImportedFeature[];
}

/** Map files you imported (GPX/KML/GeoJSON), stored only in this phone's browser. */
export function useImported() {
  const [layers, setLayers] = useState<ImportedLayer[]>([]);
  useEffect(() => {
    const read = () => setLayers(loadList<ImportedLayer>(KEY));
    read();
    window.addEventListener(EVENT, read);
    return () => window.removeEventListener(EVENT, read);
  }, []);

  const commit = useCallback((list: ImportedLayer[]) => {
    const ok = save(KEY, list);
    window.dispatchEvent(new Event(EVENT));
    return ok;
  }, []);

  const geojson = useMemo(
    () =>
      layers.length
        ? {
            type: "FeatureCollection" as const,
            features: layers.flatMap((l) => l.features.map((f) => ({ ...f, properties: { ...f.properties, layer: l.name } }))),
          }
        : null,
    [layers],
  );

  return {
    layers,
    geojson,
    importFile: async (file: File): Promise<{ layer: ImportedLayer; warnings: string[] }> => {
      if (file.size > MAX_FILE_BYTES) throw new Error("That file is too big to keep on the phone (over 3 MB). Export just the area or waypoints you need.");
      const res = parseFile(file.name, await file.text());
      const layer: ImportedLayer = {
        id: newId("imp"),
        name: file.name.replace(/\.(gpx|kml|geojson|json)$/i, ""),
        importedAt: new Date().toISOString(),
        points: res.points,
        lines: res.lines,
        areas: res.areas,
        features: res.features,
      };
      if (!commit([layer, ...loadList<ImportedLayer>(KEY)])) {
        commit(loadList<ImportedLayer>(KEY));
        throw new Error("The phone's storage for this app is full. Remove an imported file and try again.");
      }
      return { layer, warnings: res.warnings };
    },
    removeLayer: (id: string) => commit(loadList<ImportedLayer>(KEY).filter((l) => l.id !== id)),
  };
}
