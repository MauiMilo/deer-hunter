import { describe, expect, it } from "vitest";
import { sightingRate, toGpx, waypointsGeoJson, type Waypoint } from "../fieldlog";

const wp = (o: Partial<Waypoint> = {}): Waypoint => ({
  id: "w1",
  kind: "Scrape",
  name: "Big scrape <ridge>",
  lon: -71.391234567,
  lat: 45.051234567,
  accuracyM: 5,
  at: "2026-10-10T11:00:00.000Z",
  note: "Fresh & pawed",
  ...o,
});

describe("field log", () => {
  it("writes valid, escaped GPX", () => {
    const gpx = toGpx([wp()]);
    expect(gpx).toContain('<wpt lat="45.051235" lon="-71.391235">');
    expect(gpx).toContain("<name>Big scrape &lt;ridge&gt;</name>");
    expect(gpx).toContain("<desc>Scrape: Fresh &amp; pawed</desc>");
    expect(gpx.startsWith('<?xml version="1.0"')).toBe(true);
  });

  it("computes sightings per hour and ignores bad entries", () => {
    const r = sightingRate([
      { id: "a", date: "2026-10-10", window: "morning", placeId: null, placeName: "", deerSeen: 2, hours: 3, note: "" },
      { id: "b", date: "2026-10-11", window: "evening", placeId: null, placeName: "", deerSeen: 1, hours: 1, note: "" },
      { id: "c", date: "2026-10-12", window: "evening", placeId: null, placeName: "", deerSeen: -4, hours: -1, note: "" },
    ]);
    expect(r).toEqual({ hours: 4, deer: 3, perHour: 0.75, sits: 3 });
    expect(sightingRate([]).perHour).toBeNull();
  });

  it("maps waypoints for the map layer", () => {
    const fc = waypointsGeoJson([wp()]);
    expect(fc.features[0].geometry.coordinates).toEqual([-71.391234567, 45.051234567]);
  });
});
