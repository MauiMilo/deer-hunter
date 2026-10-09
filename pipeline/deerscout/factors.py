"""Factor functions for the Property Quality Score that use the Phase 2 analyses.

Each one reads `signals` gathered for a unit (land cover shares, road distances, terrain stats,
regional harvest) and returns a 0-100 value with plain-language evidence. Thresholds live in
data/scoring.yaml so they can be tuned; the reasoning is in RESEARCH.md.
"""

from __future__ import annotations

from typing import Any

from .scoring import FactorResult, ramp, register


def _pct(x: float) -> str:
    return f"{100 * x:.0f}%"


def habitat_factor(s: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    lc = s.get("landcover")
    if not lc:
        return FactorResult("habitat", None, "none", "missing", ["Land cover hasn't been analyzed for this unit."])
    c = cfg["habitat"]
    sh = lc["lc_shares"]
    food = lc["food_openings"]
    food_sc = ramp(food, c["food_low"], c["food_good"]) * (1 - 0.6 * ramp(food, c["open_too_much"], c["open_max"]))
    recent = lc.get("recent_opening_share")
    if recent is not None:
        # Fresh cuts grow the most browse; give them extra weight within the food part.
        food_sc = min(1.0, food_sc + 0.5 * ramp(recent, 0.0, c["recent_cut_good"]))
    cover_sc = ramp(lc["forest"], c["forest_low"], c["forest_good"])
    edge_sc = ramp(lc["edge_m_per_ha"], c["edge_low"], c["edge_good"])
    conifer_sc = ramp(lc["conifer_share_of_forest"], c["conifer_low"], c["conifer_good"])
    w = c["parts"]
    value = 100 * (w["food"] * food_sc + w["cover"] * cover_sc + w["edge"] * edge_sc + w["conifer"] * conifer_sc) / sum(w.values())
    dev = sh.get("developed", 0.0)
    dev_pen = ramp(dev, c["dev_low"], c["dev_high"])
    value *= 1 - 0.5 * dev_pen

    ev = [
        f"Young regrowth, brush and openings: {_pct(food)} (regrowth/brush {_pct(sh['young'])}, grass {_pct(sh['herbaceous'])}, fields {_pct(sh['agriculture'])}).",
    ]
    if recent is not None:
        y0, y1 = lc["change_years"]
        if recent >= 0.01:
            ev.append(f"{_pct(recent)} went from forest to brush or open ground between {y0} and {y1}, most likely logging.")
        else:
            ev.append(f"No new cutting picked up between {y0} and {y1}; the regrowth here is older.")
    ev += [
        f"Forest: {_pct(lc['forest'])}, about {_pct(lc['conifer_share_of_forest'])} of it softwood or mixed.",
        f"Forest-to-opening edge: {lc['edge_m_per_ha']:.0f} m per hectare.",
    ]
    if food < c["food_low"]:
        ev.append("Very little young growth or openings mapped, so food may be thin.")
    if food > c["open_too_much"]:
        ev.append("Mostly open ground: good food but little daytime cover.")
    if dev > c["dev_low"]:
        ev.append(f"{_pct(dev)} developed land (homes, roads, clearings) inside the unit.")
    ev.append(f"From {s.get('landcover_product', 'NLCD')} at 30 m. Small cuts, food plots and mast trees can be missed.")
    conf = "medium" if lc["lc_pixels"] >= 200 else "low"
    return FactorResult(
        "habitat",
        value,
        conf,
        "supported",
        ev,
        {"food": round(food_sc, 3), "cover": round(cover_sc, 3), "edge": round(edge_sc, 3), "conifer": round(conifer_sc, 3)},
    )


def pressure_factor(s: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    """Estimated pressure index. Higher score = less estimated human activity. Not a hunter count."""
    if "share_near_road" not in s:
        return FactorResult("pressure", None, "none", "missing", ["Roads and trails haven't been analyzed for this unit."])
    c = cfg["pressure"]
    near = s["share_near_road"]
    interior = s.get("share_interior", 0.0)
    trail = s.get("trail_km_per_km2")
    parts = [(1 - near, c["near_road_weight"]), (ramp(interior, 0.0, c["interior_full"]), c["interior_weight"])]
    if trail is not None:
        parts.append((1 - ramp(trail, c["trail_low"], c["trail_high"]), c["trail_weight"]))
    value = 100 * sum(v * w for v, w in parts) / sum(w for _, w in parts)
    ev = [
        f"{_pct(near)} of the unit is within a quarter mile of a drivable road; {_pct(interior)} is more than half a mile from one.",
    ]
    if trail is not None:
        ev.append(f"Mapped recreation trails: {trail:.1f} km per square km nearby.")
    ev.append("Estimated from road and trail access only. No hunter counts exist; parking areas and word of mouth aren't captured.")
    return FactorResult("pressure", value, "low", "heuristic", ev, {"near": near, "interior": interior, "trail": trail})


def access_factor(s: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    """Practical huntability: room to hunt (size, shape) and how hard it is to get in and drag a deer out."""
    from .scoring import log_ramp

    c = cfg["access"]
    size = log_ramp(s.get("acres"), c["size_floor_acres"], c["size_full_acres"])
    shape = ramp(s.get("compactness"), c["shape_floor"], c["shape_full"])
    if size is None:
        return FactorResult("access", None, "none", "missing", ["Area could not be measured."])
    parts = [(size, c["size_share"])]
    if shape is not None:
        parts.append((shape, c["shape_share"]))
    ev = [f"{s['acres']:,.0f} acres in this unit."]
    road = s.get("road_min_dist_m")
    if road is not None:
        reach = 1 - 0.9 * ramp(road, c["road_easy_m"], c["road_far_m"])
        parts.append((reach, c["road_share"]))
        name = s.get("nearest_road_name")
        if road < 50:
            ev.append(f"A drivable road touches the unit{f' ({name})' if name else ''}.")
        else:
            ev.append(f"Nearest drivable road{f' ({name})' if name else ''} is {road / 1609.34:.1f} mi away.")
        center = s.get("center_to_road_m")
        if center is not None and center > 2400:
            ev.append(f"The middle of the unit is {center / 1609.34:.1f} mi from a road: a long drag out.")
    else:
        ev.append("Road access not analyzed yet.")
    value = 100 * sum(v * w for v, w in parts) / sum(w for _, w in parts)
    if shape is not None and shape < 0.3:
        ev.append("Long or narrow shape: easy to wander over a boundary.")
    if s.get("boundary_accuracy_code") in (3, 4, 5):
        ev.append("Mapped boundary accuracy is only fair/poor; actual lines may differ.")
    conf = "medium" if road is not None else "low"
    return FactorResult("access", value, conf, "heuristic", ev, {"size": size, "shape": shape})


def terrain_factor(s: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    t = s.get("terrain")
    if not t:
        return FactorResult("terrain", None, "none", "missing", ["LiDAR terrain hasn't been analyzed for this unit."])
    c = cfg["terrain"]
    km2 = max(s["acres"] / 247.105, 0.05)
    n_feat = s.get("saddles", 0) + s.get("benches", 0)
    density = n_feat / km2
    feat_sc = ramp(density, 0.0, c["features_per_km2_good"])
    relief_sc = ramp(t["relief_m"], c["relief_low"], c["relief_good"])
    steep_pen = ramp(t["steep_share"], c["steep_bad_low"], c["steep_bad_high"])
    value = 100 * (0.6 * feat_sc + 0.4 * relief_sc) * (1 - 0.6 * steep_pen)
    ev = [
        f"{s.get('saddles', 0)} saddle(s) and {s.get('benches', 0)} bench(es) found in the elevation data.",
        f"Relief about {t['relief_m'] * 3.281:.0f} ft; average slope {t['mean_slope_deg']:.0f}°.",
    ]
    if t["steep_share"] > c["steep_bad_low"]:
        ev.append(f"{_pct(t['steep_share'])} is steeper than 30°: hard going, which isn't counted as a plus.")
    if t["relief_m"] < c["relief_low"]:
        ev.append("Mostly flat ground: fewer terrain funnels, travel follows cover and wetland edges instead.")
    ev.append(f"Bare-earth elevation at {t['dem_res_m']:.0f} m from USGS 3DEP. Shapes in the ground are candidates, not proof deer use them.")
    return FactorResult("terrain", value, "low", "heuristic", ev, {"features": feat_sc, "relief": relief_sc, "steep_penalty": steep_pen})


def abundance_factor(s: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    a = s.get("abundance")
    if not a:
        return FactorResult("abundance", None, "none", "missing", ["Deer harvest data for this WMU hasn't been loaded yet."])
    c = cfg["abundance"]
    v = a["buck_kill_per_sqmi"]
    value = 100 * ramp(v, c["low"], c["high"])
    ev = [
        f"WMU {a['wmu']}: {v:.2f} adult bucks taken per square mile in {a['year']} (Fish and Game's main deer-abundance index).",
        "A regional average: it says nothing about this specific block.",
    ]
    return FactorResult("abundance", value, "medium", "fact", ev, {"buck_kill_per_sqmi": v})


def install() -> None:
    register("habitat", habitat_factor)
    register("pressure", pressure_factor)
    register("access", access_factor)
    register("terrain", terrain_factor)
    register("abundance", abundance_factor)
