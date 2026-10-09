"""Candidate scouting spots inside each unit, built from terrain features plus habitat and access.

A spot is somewhere worth walking to and checking for sign, not a promise of deer. Each spot
says why it was picked, how confident that is, and which winds suit it: winds that blow
ACROSS the likely travel direction carry your scent away from the deer's path instead of
down it.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage

from .landcover import FOREST, OPENING, LandCover
from .terrain import Feature

BASE = {"saddle": 55.0, "bench": 50.0}


def edge_distance_m(lc: LandCover | None, x: float, y: float, radius_m: float = 300.0) -> float | None:
    """Distance from a point to the nearest forest/opening boundary in the land cover (meters)."""
    if lc is None:
        return None
    inv = ~lc.transform
    col, row = inv @ (x, y)
    r = int(radius_m / 30) + 2
    r0, c0 = int(row) - r, int(col) - r
    h, w = lc.data.shape
    if r0 < 0 or c0 < 0 or r0 + 2 * r >= h or c0 + 2 * r >= w:
        return None
    win = lc.data[r0 : r0 + 2 * r + 1, c0 : c0 + 2 * r + 1]
    forest = np.isin(win, FOREST)
    opening = np.isin(win, OPENING)
    edge = (forest & (ndimage.binary_dilation(opening))) | (opening & ndimage.binary_dilation(forest))
    if not edge.any():
        return None
    d = ndimage.distance_transform_edt(~edge) * 30.0
    return float(d[r, r])


def cover_at(lc: LandCover | None, x: float, y: float) -> int | None:
    if lc is None:
        return None
    col, row = ~lc.transform @ (x, y)
    r, c = int(row), int(col)
    if 0 <= r < lc.data.shape[0] and 0 <= c < lc.data.shape[1]:
        return int(lc.data[r, c])
    return None


def bearing_deg(x0: float, y0: float, x1: float, y1: float) -> float:
    return (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360) % 360


def good_winds(travel_axis_deg: float, half_width: float = 45.0) -> list[list[float]]:
    """Wind-FROM directions roughly perpendicular to the travel axis (two arcs, degrees)."""
    out = []
    for center in ((travel_axis_deg + 90) % 360, (travel_axis_deg + 270) % 360):
        out.append([round((center - half_width) % 360, 1), round((center + half_width) % 360, 1)])
    return out


def score_spot(
    f: Feature,
    *,
    edge_m: float | None,
    cover_class: int | None,
    road_m: float | None,
    trail_m: float | None,
    boundary_m: float,
) -> tuple[float, str, list[str]]:
    score = BASE[f.kind]
    why = list(f.notes)
    if f.kind == "saddle":
        why.append(f"Saddle about {f.area_m2 / 4046.86:.1f} acres in size.")
    else:
        why.append(f"Bench about {f.area_m2 / 4046.86:.1f} acres in size, average slope here {f.slope_deg:.0f}°.")
    if f.area_m2 > 6000:
        score += 5

    if edge_m is not None:
        if edge_m <= 150:
            score += 15
            where = "Right on a forest/opening edge" if edge_m < 30 else f"Within {edge_m:.0f} m of a forest/opening edge"
            why.append(f"{where}: food and cover meet close by.")
        elif edge_m <= 300:
            score += 8
            why.append(f"About {edge_m:.0f} m from a forest/opening edge.")
    if cover_class in FOREST:
        score += 5
    elif cover_class in OPENING:
        why.append("The spot itself maps as open or brushy ground; set up on the timber edge.")

    if road_m is not None:
        if road_m < 150:
            score -= 10
            why.append(f"Only {road_m:.0f} m from a drivable road: likely disturbed.")
        elif road_m <= 1500:
            score += 10
            why.append(f"{road_m / 1609.34:.1f} mi walk from the nearest drivable road.")
        elif road_m > 3000:
            score -= 10
            why.append(f"{road_m / 1609.34:.1f} mi from a road: long drag if you get one.")
    if trail_m is not None and trail_m < 100:
        score -= 5
        why.append("A mapped recreation trail passes within 100 m.")
    if boundary_m < 100:
        score -= 10
        why.append(f"Only {boundary_m:.0f} m inside the mapped boundary; check lines and posting.")
    if f.slope_deg > 25:
        score -= 5

    have = sum(v is not None for v in (edge_m, road_m))
    confidence = "medium" if have == 2 else "low"
    return max(0.0, min(100.0, score)), confidence, why


def spot_record(
    f: Feature,
    unit_id: str,
    property_id: str,
    lonlat: tuple[float, float],
    score: float,
    confidence: str,
    why: list[str],
    road_info: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "id": f"{unit_id}#{f.kind[0]}{int(f.x) % 100000}{int(f.y) % 100000}",
        "unit_id": unit_id,
        "property_id": property_id,
        "kind": f.kind,
        "point": [round(lonlat[0], 5), round(lonlat[1], 5)],
        "elevation_ft": round(f.elevation_m * 3.28084),
        "slope_deg": round(f.slope_deg, 1),
        "score": round(score),
        "confidence": confidence,
        "reasons": why,
        "travel_axis_deg": f.travel_axis_deg,
        "good_winds_from": good_winds(f.travel_axis_deg),
        "approach": road_info,
    }
