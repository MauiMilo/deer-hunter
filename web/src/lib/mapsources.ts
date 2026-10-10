// Map tile sources. All are public-domain US government services (USGS The National Map / 3DEP),
// except the label font, which comes from the MapLibre demo server.

export const USGS = "https://basemap.nationalmap.gov/arcgis/rest/services";
export const TOPO_TILES = `${USGS}/USGSTopo/MapServer/tile/{z}/{y}/{x}`;
export const IMAGERY_TILES = `${USGS}/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}`;
export const HILLSHADE_BASE = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage";
export const HILLSHADE_TILES =
  HILLSHADE_BASE +
  "?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&size=256,256&format=png&f=image" +
  "&renderingRule=" +
  encodeURIComponent(JSON.stringify({ rasterFunction: "Hillshade Multidirectional" }));
export const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";
export const LABEL_FONT = "Open Sans Semibold";

export const MAXZOOM = { topo: 16, imagery: 16, hillshade: 17 } as const;
export const HILLSHADE_MINZOOM = 8;
