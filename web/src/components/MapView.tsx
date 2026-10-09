"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MlMap, MapLayerMouseEvent, StyleSpecification } from "maplibre-gl";

export type BaseLayer = "topo" | "imagery" | "hillshade";

export const BASE_LABELS: Record<BaseLayer, string> = {
  topo: "Topo",
  imagery: "Satellite",
  hillshade: "LiDAR relief",
};

// All public-domain US government services (USGS The National Map / 3DEP).
const USGS = "https://basemap.nationalmap.gov/arcgis/rest/services";
const HILLSHADE =
  "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage" +
  "?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png&f=image" +
  "&renderingRule=" +
  encodeURIComponent(JSON.stringify({ rasterFunction: "Hillshade Multidirectional" }));

const ATTR = '<a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank">USGS The National Map</a> · Lands: <a href="https://granit.unh.edu" target="_blank">NH GRANIT</a>';

function style(): StyleSpecification {
  return {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    sources: {
      topo: { type: "raster", tiles: [`${USGS}/USGSTopo/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 16, attribution: ATTR },
      imagery: { type: "raster", tiles: [`${USGS}/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}`], tileSize: 256, maxzoom: 16, attribution: ATTR },
      hillshade: { type: "raster", tiles: [HILLSHADE], tileSize: 256, minzoom: 8, maxzoom: 17, attribution: ATTR },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "#d9d6cc" } },
      { id: "topo", type: "raster", source: "topo", layout: { visibility: "visible" } },
      { id: "imagery", type: "raster", source: "imagery", layout: { visibility: "none" } },
      { id: "hillshade", type: "raster", source: "hillshade", layout: { visibility: "none" } },
    ],
  };
}

const STATUS_COLOR = ["match", ["get", "status"], "verified", "#2fbf71", "prohibited", "#e5534b", "#e3b341"] as unknown as string;

interface Props {
  className?: string;
  base?: BaseLayer;
  fitBbox?: [number, number, number, number] | null;
  center?: [number, number];
  zoom?: number;
  highlightPropertyId?: string | null;
  highlightUnitId?: string | null;
  showBlocks?: boolean;
  showLocate?: boolean;
  onSelectProperty?: (id: string) => void;
  onSelectUnit?: (id: string) => void;
}

export default function MapView({
  className = "",
  base = "topo",
  fitBbox,
  center = [-71.3, 45.05],
  zoom = 9,
  highlightPropertyId = null,
  highlightUnitId = null,
  showBlocks = true,
  showLocate = true,
  onSelectProperty,
  onSelectUnit,
}: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const handlers = useRef({ onSelectProperty, onSelectUnit });
  useEffect(() => {
    handlers.current = { onSelectProperty, onSelectUnit };
  }, [onSelectProperty, onSelectUnit]);

  useEffect(() => {
    let disposed = false;
    (async () => {
      const ml = await import("maplibre-gl");
      if (disposed || !el.current) return;
      const m = new ml.Map({
        container: el.current,
        style: style(),
        center,
        zoom,
        maxZoom: 17.5,
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
      });
      map.current = m;
      m.touchZoomRotate.disableRotation();
      m.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      m.addControl(new ml.ScaleControl({ unit: "imperial" }), "bottom-left");
      if (showLocate) {
        m.addControl(
          new ml.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true, showAccuracyCircle: true }),
          "top-right",
        );
      }
      m.on("error", (e) => {
        const msg = (e as { error?: Error }).error?.message ?? "";
        if (/properties|blocks/.test(msg)) setFailed("Property boundaries couldn't load.");
      });
      m.on("load", () => {
        m.addSource("properties", { type: "geojson", data: "/data/properties.geojson", promoteId: "id" });
        m.addSource("blocks", { type: "geojson", data: "/data/blocks.geojson", promoteId: "id" });
        m.addLayer({ id: "prop-fill", type: "fill", source: "properties", paint: { "fill-color": STATUS_COLOR, "fill-opacity": 0.18 } });
        m.addLayer({ id: "prop-line", type: "line", source: "properties", paint: { "line-color": STATUS_COLOR, "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.8, 13, 2.2] } });
        m.addLayer({
          id: "block-line",
          type: "line",
          source: "blocks",
          minzoom: 10.5,
          paint: { "line-color": "#1b1b1b", "line-opacity": 0.45, "line-width": 1, "line-dasharray": [2, 2] },
        });
        m.addLayer({
          id: "block-label",
          type: "symbol",
          source: "blocks",
          minzoom: 11.5,
          layout: {
            "text-field": ["concat", ["slice", ["get", "label"], 6], "\n", ["to-string", ["coalesce", ["get", "score"], "–"]]],
            "text-font": ["Open Sans Semibold"],
            "text-size": 12,
          },
          paint: { "text-color": "#111", "text-halo-color": "#fff", "text-halo-width": 1.6 },
        });
        m.addLayer({ id: "prop-hl", type: "line", source: "properties", filter: ["==", ["get", "id"], ""], paint: { "line-color": "#ff6b1a", "line-width": 4 } });
        m.addLayer({ id: "block-hl", type: "line", source: "blocks", filter: ["==", ["get", "id"], ""], paint: { "line-color": "#ff6b1a", "line-width": 3.5 } });
        m.addLayer({
          id: "prop-label",
          type: "symbol",
          source: "properties",
          minzoom: 10,
          layout: { "text-field": ["get", "name"], "text-font": ["Open Sans Semibold"], "text-size": 12, "symbol-placement": "point", "text-max-width": 10 },
          paint: { "text-color": "#102018", "text-halo-color": "#fff", "text-halo-width": 1.5 },
        });

        m.addLayer({ id: "block-hit", type: "fill", source: "blocks", minzoom: 10.5, paint: { "fill-opacity": 0 } }, "block-line");

        const click = (e: MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f) return;
          // Zoomed in on a big property: a tap picks the block under your finger.
          if (handlers.current.onSelectUnit && m.getZoom() >= 10.5) {
            const block = m.queryRenderedFeatures(e.point, { layers: ["block-hit"] })[0];
            if (block) {
              handlers.current.onSelectUnit(String(block.properties?.id));
              return;
            }
          }
          handlers.current.onSelectProperty?.(String(f.properties?.id));
        };
        m.on("click", "prop-fill", click);
        m.on("mouseenter", "prop-fill", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "prop-fill", () => (m.getCanvas().style.cursor = ""));
        setReady(true);
      });
    })().catch((e: Error) => setFailed(`Map couldn't start: ${e.message}`));
    return () => {
      disposed = true;
      map.current?.remove();
      map.current = null;
    };
    // The map is created once; later prop changes are applied by the effects below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const b of ["topo", "imagery", "hillshade"] as const) m.setLayoutProperty(b, "visibility", b === base ? "visible" : "none");
  }, [base, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    m.setFilter("prop-hl", ["==", ["get", "id"], highlightPropertyId ?? ""]);
    m.setFilter("block-hl", ["==", ["get", "id"], highlightUnitId ?? ""]);
  }, [highlightPropertyId, highlightUnitId, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const id of ["block-line", "block-label"]) m.setLayoutProperty(id, "visibility", showBlocks ? "visible" : "none");
  }, [showBlocks, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !fitBbox) return;
    m.fitBounds(
      [
        [fitBbox[0], fitBbox[1]],
        [fitBbox[2], fitBbox[3]],
      ],
      { padding: 36, maxZoom: 14, duration: 600 },
    );
  }, [fitBbox, ready]);

  return (
    <div className={`relative overflow-hidden ${className}`}>
      {/* Inline position: maplibre's own CSS (unlayered) would otherwise override Tailwind's "absolute". */}
      <div ref={el} style={{ position: "absolute", inset: 0 }} />
      {failed && (
        <div className="absolute inset-x-3 top-3 rounded-lg bg-bad/90 px-3 py-2 text-sm text-white">{failed}</div>
      )}
    </div>
  );
}
