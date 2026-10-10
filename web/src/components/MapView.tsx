"use client";

import { useEffect, useRef, useState } from "react";
import type { Map as MlMap, MapLayerMouseEvent, StyleSpecification } from "maplibre-gl";

export type BaseLayer = "topo" | "imagery" | "hillshade";

export const BASE_LABELS: Record<BaseLayer, string> = {
  topo: "Topo",
  imagery: "Satellite",
  hillshade: "LiDAR relief",
};

import { GLYPHS, HILLSHADE_MINZOOM, HILLSHADE_TILES, IMAGERY_TILES, LABEL_FONT, MAXZOOM, TOPO_TILES } from "@/lib/mapsources";

const ATTR = '<a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank">USGS The National Map</a> · Lands: <a href="https://granit.unh.edu" target="_blank">NH GRANIT</a>';

function style(): StyleSpecification {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      topo: { type: "raster", tiles: [TOPO_TILES], tileSize: 256, maxzoom: MAXZOOM.topo, attribution: ATTR },
      imagery: { type: "raster", tiles: [IMAGERY_TILES], tileSize: 256, maxzoom: MAXZOOM.imagery, attribution: ATTR },
      hillshade: { type: "raster", tiles: [HILLSHADE_TILES], tileSize: 256, minzoom: HILLSHADE_MINZOOM, maxzoom: MAXZOOM.hillshade, attribution: ATTR },
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
  landcover?: { coordinates: [[number, number], [number, number], [number, number], [number, number]] } | null;
  showLandcover?: boolean;
  showSpots?: boolean;
  highlightSpotId?: string | null;
  onSelectSpot?: (id: string) => void;
  /** Your own waypoints (kept on the phone), drawn as markers. */
  waypoints?: { type: "FeatureCollection"; features: unknown[] } | null;
  base?: BaseLayer;
  fitBbox?: [number, number, number, number] | null;
  /** How far in fitBbox may zoom (default 14; a spot close-up goes further). */
  fitMaxZoom?: number;
  /** Your imported GPX/KML/GeoJSON layers (kept on the phone). */
  imported?: { type: "FeatureCollection"; features: unknown[] } | null;
  /** Called with the visible map box (west, south, east, north) and zoom after the map moves. */
  onView?: (bbox: [number, number, number, number], zoom: number) => void;
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
  fitMaxZoom = 14,
  imported = null,
  onView,
  center = [-71.3, 45.05],
  zoom = 9,
  highlightPropertyId = null,
  highlightUnitId = null,
  showBlocks = true,
  showLocate = true,
  landcover = null,
  showLandcover = false,
  showSpots = true,
  highlightSpotId = null,
  waypoints = null,
  onSelectProperty,
  onSelectUnit,
  onSelectSpot,
}: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const handlers = useRef({ onSelectProperty, onSelectUnit, onSelectSpot, onView });
  useEffect(() => {
    handlers.current = { onSelectProperty, onSelectUnit, onSelectSpot, onView };
  }, [onSelectProperty, onSelectUnit, onSelectSpot, onView]);

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
      const report = () => {
        const b = m.getBounds();
        handlers.current.onView?.([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], m.getZoom());
      };
      m.on("moveend", report);
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
            "text-font": [LABEL_FONT],
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
          layout: { "text-field": ["get", "name"], "text-font": [LABEL_FONT], "text-size": 12, "symbol-placement": "point", "text-max-width": 10 },
          paint: { "text-color": "#102018", "text-halo-color": "#fff", "text-halo-width": 1.5 },
        });

        m.addLayer({ id: "block-hit", type: "fill", source: "blocks", minzoom: 10.5, paint: { "fill-opacity": 0 } }, "block-line");

        const click = (e: MapLayerMouseEvent) => {
          const f = e.features?.[0];
          if (!f) return;
          // A tap on a spot dot is handled by the spot layer.
          if (m.getLayer("spot-dot") && m.queryRenderedFeatures(e.point, { layers: ["spot-dot"] }).length) return;
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

        // Scouting spots: saddles and benches picked from the elevation data.
        m.addSource("spots", { type: "geojson", data: "/data/spots.geojson", promoteId: "id" });
        m.addLayer({
          id: "spot-dot",
          type: "circle",
          source: "spots",
          minzoom: 10.5,
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 10.5, 3.5, 15, 9],
            "circle-color": ["interpolate", ["linear"], ["get", "score"], 30, "#9aa79f", 60, "#ffb27a", 80, "#ff6b1a"],
            "circle-stroke-color": "#111",
            "circle-stroke-width": 1.2,
          },
        });
        m.addLayer({
          id: "spot-label",
          type: "symbol",
          source: "spots",
          minzoom: 12.5,
          layout: {
            "text-field": ["concat", ["match", ["get", "kind"], "saddle", "Saddle ", "Bench "], ["to-string", ["get", "score"]]],
            "text-font": [LABEL_FONT],
            "text-size": 11,
            "text-offset": [0, 1.2],
            "text-anchor": "top",
          },
          paint: { "text-color": "#111", "text-halo-color": "#fff", "text-halo-width": 1.5 },
        });
        m.addLayer({
          id: "spot-hl",
          type: "circle",
          source: "spots",
          filter: ["==", ["get", "id"], ""],
          paint: { "circle-radius": 13, "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#ff6b1a", "circle-stroke-width": 3 },
        });
        m.on("click", "spot-dot", (e) => {
          const id = e.features?.[0]?.properties?.id;
          if (id) handlers.current.onSelectSpot?.(String(id));
        });
        m.on("mouseenter", "spot-dot", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "spot-dot", () => (m.getCanvas().style.cursor = ""));
        m.on("mouseenter", "prop-fill", () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", "prop-fill", () => (m.getCanvas().style.cursor = ""));
        setReady(true);
        report();
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
    if (!m || !ready || !waypoints) return;
    const data = waypoints as unknown as GeoJSON.FeatureCollection;
    const src = m.getSource("waypoints") as import("maplibre-gl").GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
      return;
    }
    m.addSource("waypoints", { type: "geojson", data });
    m.addLayer({
      id: "wp-dot",
      type: "circle",
      source: "waypoints",
      paint: { "circle-radius": 6, "circle-color": "#6cb6ff", "circle-stroke-color": "#08203a", "circle-stroke-width": 2 },
    });
    m.addLayer({
      id: "wp-label",
      type: "symbol",
      source: "waypoints",
      minzoom: 12,
      layout: { "text-field": ["get", "name"], "text-font": [LABEL_FONT], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top" },
      paint: { "text-color": "#08203a", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
  }, [waypoints, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !landcover) return;
    if (!m.getSource("landcover")) {
      m.addSource("landcover", { type: "image", url: "/data/landcover.png", coordinates: landcover.coordinates });
      m.addLayer({ id: "landcover", type: "raster", source: "landcover", paint: { "raster-opacity": 0.75, "raster-resampling": "nearest" }, layout: { visibility: "none" } }, "prop-fill");
    }
    m.setLayoutProperty("landcover", "visibility", showLandcover ? "visible" : "none");
  }, [landcover, showLandcover, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !m.getLayer("spot-dot")) return;
    for (const id of ["spot-dot", "spot-label", "spot-hl"]) m.setLayoutProperty(id, "visibility", showSpots ? "visible" : "none");
    m.setFilter("spot-hl", ["==", ["get", "id"], highlightSpotId ?? ""]);
  }, [showSpots, highlightSpotId, ready]);

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
      { padding: 36, maxZoom: fitMaxZoom, duration: 600 },
    );
  }, [fitBbox, fitMaxZoom, ready]);

  useEffect(() => {
    const m = map.current;
    if (!m || !ready || !imported) return;
    const data = imported as unknown as GeoJSON.FeatureCollection;
    const src = m.getSource("imported") as import("maplibre-gl").GeoJSONSource | undefined;
    if (src) {
      src.setData(data);
      return;
    }
    m.addSource("imported", { type: "geojson", data });
    m.addLayer({
      id: "imp-line",
      type: "line",
      source: "imported",
      filter: ["in", ["geometry-type"], ["literal", ["LineString", "MultiLineString", "Polygon", "MultiPolygon"]]],
      paint: { "line-color": "#c15cff", "line-width": 3 },
    });
    m.addLayer({
      id: "imp-dot",
      type: "circle",
      source: "imported",
      filter: ["==", ["geometry-type"], "Point"],
      paint: { "circle-radius": 6, "circle-color": "#c15cff", "circle-stroke-color": "#fff", "circle-stroke-width": 2 },
    });
    m.addLayer({
      id: "imp-label",
      type: "symbol",
      source: "imported",
      minzoom: 12,
      filter: ["==", ["geometry-type"], "Point"],
      layout: { "text-field": ["coalesce", ["get", "name"], ""], "text-font": [LABEL_FONT], "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top" },
      paint: { "text-color": "#3a0f52", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
  }, [imported, ready]);

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
