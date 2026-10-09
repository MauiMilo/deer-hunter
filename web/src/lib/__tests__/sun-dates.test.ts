import { describe, expect, it } from "vitest";
import { addDays, labelDay, nextSaturday, ymdInTz } from "../dates";
import { legalHours, sunTimes } from "../sun";

const minutesUTC = (d: Date) => d.getUTCHours() * 60 + d.getUTCMinutes() + d.getUTCSeconds() / 60;

describe("sunrise and sunset", () => {
  it("matches published Boston solstice times within a few minutes", () => {
    // Boston, June 20 2024: sunrise 5:07 AM EDT (09:07 UTC), sunset 8:25 PM EDT (00:25 UTC next day).
    const s = sunTimes("2024-06-20", 42.3601, -71.0589)!;
    expect(Math.abs(minutesUTC(s.sunrise) - (9 * 60 + 7))).toBeLessThan(4);
    expect(Math.abs(minutesUTC(s.sunset) - 25)).toBeLessThan(4);
  });

  it("gives about 12 hours of daylight at the equator on an equinox", () => {
    const s = sunTimes("2024-03-20", 0, 0)!;
    const hours = (s.sunset.getTime() - s.sunrise.getTime()) / 3600000;
    expect(hours).toBeGreaterThan(12.0);
    expect(hours).toBeLessThan(12.2);
  });

  it("gives plausible October times in Pittsburg, NH", () => {
    const s = sunTimes("2026-10-10", 45.05, -71.4)!;
    const hours = (s.sunset.getTime() - s.sunrise.getTime()) / 3600000;
    expect(hours).toBeGreaterThan(10.8);
    expect(hours).toBeLessThan(11.4);
    expect(minutesUTC(s.sunrise)).toBeGreaterThan(10 * 60 + 40); // after 6:40 AM EDT
    expect(minutesUTC(s.sunrise)).toBeLessThan(11 * 60 + 20); // before 7:20 AM EDT
    expect(ymdInTz(s.sunrise)).toBe("2026-10-10");
  });

  it("legal hours run 30 minutes past each end", () => {
    const l = legalHours("2026-10-10", 45.05, -71.4)!;
    expect(l.sunrise.getTime() - l.start.getTime()).toBe(30 * 60000);
    expect(l.end.getTime() - l.sunset.getTime()).toBe(30 * 60000);
  });
});

describe("dates", () => {
  it("adds days across month and year ends", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-08", 1)).toBe("2026-03-09");
  });

  it("finds the coming Saturday", () => {
    expect(nextSaturday("2026-10-08")).toBe("2026-10-10"); // Thursday -> Saturday
    expect(nextSaturday("2026-10-10")).toBe("2026-10-10");
    expect(nextSaturday("2026-10-11")).toBe("2026-10-17");
  });

  it("uses New Hampshire's calendar day", () => {
    // 02:00 UTC on Oct 9 is still Oct 8 in New Hampshire.
    expect(ymdInTz(new Date(Date.UTC(2026, 9, 9, 2)))).toBe("2026-10-08");
    expect(labelDay("2026-10-09", "2026-10-08")).toBe("Tomorrow");
  });
});
