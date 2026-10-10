import { describe, expect, it } from "vitest";
import { parseFile, parseGpx, parseKml } from "../importfile";
import { areaUrls, estimate, lonLatToTile, padBBox, tileBBox3857, tileKey, tilesIn } from "../offline";
import { HILLSHADE_TILES } from "../mapsources";

describe("offline tiles", () => {
  it("finds the right tile for a point", () => {
    // Pittsburg village at zoom 12.
    expect(lonLatToTile(-71.392, 45.051, 12)).toEqual({ x: 1235, y: 1472 });
  });

  it("matches MapLibre's box for a tile", () => {
    expect(tileBBox3857(0, 0, 1)).toEqual([-20037508.342789244, 0, 0, 20037508.342789244]);
  });

  it("keys hillshade tiles the same whatever the decimals", () => {
    const a = HILLSHADE_TILES.replace("{bbox-epsg-3857}", "-7952469.123456,5634675.000001,-7952316.2,5634828.1");
    const b = HILLSHADE_TILES.replace("{bbox-epsg-3857}", "-7952469.1234,5634675,-7952316.20000001,5634828.0999999");
    expect(tileKey(a)).toBe(tileKey(b));
    expect(tileKey("https://basemap.nationalmap.gov/x/1/2/3")).toBe("https://basemap.nationalmap.gov/x/1/2/3");
  });

  it("sizes a block-sized area sensibly", () => {
    const block = padBBox([-71.445, 45.082, -71.425, 45.095], 300); // about 2 km square
    const e = estimate(block, 10);
    expect(e.tiles).toBeGreaterThan(100);
    expect(e.tiles).toBeLessThan(1500);
    expect(areaUrls(block, 10).length).toBe(e.tiles + 1); // + the label font
    expect(tilesIn(block, 16).length).toBeGreaterThan(20);
  });
});

const GPX = `<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <wpt lat="45.0866" lon="-71.4338"><name>Rub line</name></wpt>
  <wpt lon="-71.43" lat="45.09"/>
  <trk><name>Walk in</name><trkseg>
    <trkpt lat="45.0873" lon="-71.4301"/><trkpt lat="45.0870" lon="-71.4320"/><trkpt lat="45.0866" lon="-71.4338"/>
  </trkseg></trk>
</gpx>`;

const KML = `<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
  <Placemark><name><![CDATA[Stand & bait]]></name><Point><coordinates>-71.25327,45.22811,0</coordinates></Point></Placemark>
  <Placemark><name>Boundary</name><Polygon><outerBoundaryIs><LinearRing><coordinates>
    -71.26,45.22,0 -71.25,45.22,0 -71.25,45.23,0 -71.26,45.23,0 -71.26,45.22,0
  </coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>
  <Placemark><name>Old road</name><LineString><coordinates>-71.25,45.22 -71.24,45.23</coordinates></LineString></Placemark>
</Document></kml>`;

describe("importing map files", () => {
  it("reads GPX waypoints and tracks", () => {
    const f = parseGpx(GPX);
    expect(f.filter((x) => x.geometry.type === "Point").map((x) => x.properties.name)).toEqual(["Rub line", "Waypoint"]);
    const trk = f.find((x) => x.geometry.type === "LineString");
    expect(trk?.properties.name).toBe("Walk in");
    expect(trk?.geometry.coordinates).toHaveLength(3);
  });

  it("reads KML points, lines and areas", () => {
    const f = parseKml(KML);
    expect(f.map((x) => x.geometry.type)).toEqual(["Point", "Polygon", "LineString"]);
    expect(f[0].properties.name).toBe("Stand & bait");
    expect(f[0].geometry.coordinates).toEqual([-71.25327, 45.22811]);
  });

  it("reads GeoJSON and counts what it found", () => {
    const r = parseFile("x.geojson", JSON.stringify({ type: "FeatureCollection", features: [{ type: "Feature", properties: { name: "A" }, geometry: { type: "MultiPoint", coordinates: [[-71, 45], [-71.1, 45.1]] } }] }));
    expect(r.points).toBe(2);
  });

  it("explains files it can't read", () => {
    expect(() => parseFile("hunt.kmz", "PK")).toThrow(/zipped/);
    expect(() => parseFile("empty.gpx", "<gpx></gpx>")).toThrow(/No waypoints/);
  });
});

import { withParking } from "../spots";
import type { Spot } from "../types";

describe("walk-in from a parking spot", () => {
  const spot = {
    id: "s", unit_id: "u", property_id: "p", kind: "bench", point: [-71.4338, 45.08663], elevation_ft: 1466, slope_deg: 2, score: 80,
    confidence: "medium", reasons: [], travel_axis_deg: 45, good_winds_from: [], approach: { road_name: null, distance_m: 298, road_bearing_deg: 60 },
  } as unknown as Spot;
  it("uses a parking spot within a mile", () => {
    const s = withParking(spot, [{ name: "Old log yard", point: [-71.43106, 45.08571] }]);
    expect(s.approach?.kind).toBe("parking");
    expect(s.approach?.distance_m).toBeGreaterThan(220);
    expect(s.approach?.distance_m).toBeLessThan(260);
  });
  it("ignores parking that's far away", () => {
    expect(withParking(spot, [{ name: "Far", point: [-71.3, 45.2] }])).toBe(spot);
  });
});
