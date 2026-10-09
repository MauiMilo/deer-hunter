import { describe, expect, it } from "vitest";
import { angleDiff, circularMean, circularSpreadDeg, compass, compassName, downwind, sectorCounts, windFavorsSetup } from "../wind";

describe("wind directions", () => {
  it("names compass points", () => {
    expect(compass(0)).toBe("N");
    expect(compass(359)).toBe("N");
    expect(compass(315)).toBe("NW");
    expect(compass(292.5)).toBe("WNW");
    expect(compass(-45)).toBe("NW");
    expect(compassName(310, )).toBe("northwest");
  });

  it("measures the short way around the circle", () => {
    expect(angleDiff(350, 10)).toBe(20);
    expect(angleDiff(10, 350)).toBe(20);
    expect(angleDiff(0, 180)).toBe(180);
    expect(angleDiff(720, 90)).toBe(90);
  });

  it("puts scent opposite the wind's source", () => {
    expect(downwind(315)).toBe(135);
    expect(downwind(90)).toBe(270);
  });

  it("averages angles across north correctly", () => {
    const m = circularMean([350, 10]);
    expect(m.meanDeg).not.toBeNull();
    expect(angleDiff(m.meanDeg!, 0)).toBeLessThan(1e-9);
    expect(m.steadiness).toBeCloseTo(Math.cos((10 * Math.PI) / 180), 9);
  });

  it("reports no prevailing direction when winds cancel", () => {
    expect(circularMean([90, 270]).meanDeg).toBeNull();
    expect(circularMean([]).meanDeg).toBeNull();
  });

  it("weights directions by speed", () => {
    const m = circularMean([0, 90], [10, 0.0001]);
    expect(angleDiff(m.meanDeg!, 0)).toBeLessThan(0.01);
  });

  it("converts steadiness to a spread", () => {
    expect(circularSpreadDeg(1)).toBe(0);
    expect(circularSpreadDeg(0)).toBe(180);
    expect(circularSpreadDeg(0.9)).toBeGreaterThan(20);
    expect(circularSpreadDeg(0.9)).toBeLessThan(30);
  });

  it("bins a wind rose", () => {
    expect(sectorCounts([0, 5, 355, 90, 180, 270, 46], 8)).toEqual([3, 1, 1, 0, 1, 0, 1, 0]);
  });

  it("judges a setup against the expected deer direction", () => {
    // Deer expected from the north.
    expect(windFavorsSetup(0, 0)).toBe("good"); // north wind blows your scent south, away from deer
    expect(windFavorsSetup(180, 0)).toBe("bad"); // south wind carries scent north, into the deer
    expect(windFavorsSetup(90, 0)).toBe("marginal"); // crosswind
    expect(windFavorsSetup(330, 0)).toBe("good");
  });
});

import { approachFit, axisDiff, spotWindFit } from "../wind";

describe("spot wind fit", () => {
  it("measures angles between lines, not directions", () => {
    expect(axisDiff(0, 180)).toBe(0);
    expect(axisDiff(10, 350)).toBe(20);
    expect(axisDiff(90, 0)).toBe(90);
    expect(axisDiff(135, 0)).toBe(45);
  });

  it("likes a crosswind on a travel route", () => {
    // Deer travel north-south through a saddle.
    expect(spotWindFit(270, 0)).toBe("good"); // west wind blows across the route
    expect(spotWindFit(90, 180)).toBe("good");
    expect(spotWindFit(10, 0)).toBe("bad"); // north wind blows down the route
    expect(spotWindFit(200, 0)).toBe("bad");
    expect(spotWindFit(35, 0)).toBe("marginal");
  });

  it("wants the wind in your face on the walk in", () => {
    // Walking north (bearing 0) into the spot.
    expect(approachFit(0, 0)).toBe("good"); // north wind in your face
    expect(approachFit(180, 0)).toBe("bad"); // south wind at your back
    expect(approachFit(90, 0)).toBe("marginal");
  });
});
