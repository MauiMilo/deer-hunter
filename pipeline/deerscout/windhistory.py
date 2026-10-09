"""Historical wind patterns from Open-Meteo's archive (hourly reanalysis), for planning.

For a few points across the region we count how often the wind blows from each direction,
by month and by time of day (morning vs evening hunting hours), using circular statistics
for the average direction. These are regional, model-based winds at 10 m height; ridges,
hollows and thermals change the wind on the ground.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .http import Session, get_json

SOURCE = "Open-Meteo historical weather"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
SECTORS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
MONTHS = [9, 10, 11, 12]  # hunting season months


def circular_mean(degs: list[float], weights: list[float] | None = None) -> tuple[float | None, float]:
    sx = sy = sw = 0.0
    for i, d in enumerate(degs):
        w = 1.0 if weights is None else max(0.0, weights[i])
        sx += w * math.cos(math.radians(d))
        sy += w * math.sin(math.radians(d))
        sw += w
    if sw == 0:
        return None, 0.0
    r = math.hypot(sx, sy) / sw
    if r < 1e-9:
        return None, 0.0
    return (math.degrees(math.atan2(sy, sx)) + 360) % 360, r


def sector(deg: float) -> int:
    return int(((deg % 360) + 22.5) // 45) % 8


def summarize(times: list[str], dirs: list[float | None], speeds: list[float | None]) -> dict[str, Any]:
    """Wind roses by month and window. `times` are local ISO strings (America/New_York)."""
    buckets: dict[tuple[int, str], dict[str, Any]] = {}
    for t, d, s in zip(times, dirs, speeds):
        if d is None or s is None:
            continue
        dt = datetime.fromisoformat(t)
        if dt.month not in MONTHS:
            continue
        hour = dt.hour
        if 5 <= hour <= 9:
            win = "morning"
        elif 14 <= hour <= 18:
            win = "evening"
        else:
            continue
        b = buckets.setdefault((dt.month, win), {"counts": [0] * 8, "calm": 0, "dirs": [], "speeds": []})
        if s < 2.0:  # mph; direction is meaningless in near-calm air
            b["calm"] += 1
            continue
        b["counts"][sector(d)] += 1
        b["dirs"].append(d)
        b["speeds"].append(s)
    out: dict[str, Any] = {}
    for (month, win), b in sorted(buckets.items()):
        n = sum(b["counts"]) + b["calm"]
        mean, r = circular_mean(b["dirs"], b["speeds"])
        speeds = sorted(b["speeds"])
        out.setdefault(str(month), {})[win] = {
            "hours": n,
            "calm_share": round(b["calm"] / n, 3) if n else None,
            "sector_share": [round(c / n, 3) if n else 0 for c in b["counts"]],
            "mean_from_deg": None if mean is None else round(mean, 1),
            "steadiness": round(r, 3),
            "median_mph": round(speeds[len(speeds) // 2], 1) if speeds else None,
            "p90_mph": round(speeds[int(len(speeds) * 0.9)], 1) if speeds else None,
        }
    return out


def fetch_point(session: Session, lat: float, lon: float, start: str, end: str) -> dict[str, Any]:
    doc = get_json(
        session,
        ARCHIVE,
        {
            "latitude": round(lat, 3),
            "longitude": round(lon, 3),
            "start_date": start,
            "end_date": end,
            "hourly": "wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "mph",
            "timezone": "America/New_York",
        },
        source=SOURCE,
        timeout=120,
    )
    h = doc.get("hourly") or {}
    return {
        "lat": doc.get("latitude", lat),
        "lon": doc.get("longitude", lon),
        "elevation_m": doc.get("elevation"),
        "seasons": summarize(h.get("time", []), h.get("wind_direction_10m", []), h.get("wind_speed_10m", [])),
    }


def history(session: Session, points: list[tuple[str, float, float]], years: int = 5) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    end_year = now.year - 1 if now.month < 12 else now.year
    start, end = f"{end_year - years + 1}-09-01", f"{end_year}-12-31"
    return {
        "period": [start, end],
        "note": "Regional model winds at 10 m. Terrain, thermals and timber change the wind where you sit.",
        "points": {key: fetch_point(session, lat, lon, start, end) for key, lat, lon in points},
    }
