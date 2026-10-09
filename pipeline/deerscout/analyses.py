"""Phase 2-3 analyses run inside a pipeline build: land cover, roads/trails, terrain + spots,
historical wind. Each step is optional: if a source fails, its factor stays "missing" and the
failure is written to the manifest. Nothing is filled in with guesses.
"""

from __future__ import annotations

import json
import logging
import math
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import geopandas as gpd
import numpy as np
import shapely
import shapely.ops
from pyproj import Transformer

from . import landcover, roads, spots, terrain, windhistory
from .config import EQUAL_AREA, WGS84
from .http import Session

log = logging.getLogger("deerscout")
_TO_WGS = Transformer.from_crs(EQUAL_AREA, WGS84, always_xy=True)
_TO_EA = Transformer.from_crs(WGS84, EQUAL_AREA, always_xy=True)

DEM_RES_M = float(os.environ.get("DEERSCOUT_DEM_RES_M", "6"))
TILE_M = 8000.0
SPOTS_PER_UNIT = 6
SPOT_MIN_SPACING_M = 150.0


@dataclass
class Context:
    session: Session
    units_ea: gpd.GeoDataFrame  # columns: id, property_id, geometry (EA meters)
    analyze_ids: set[str]  # units worth analyzing (not prohibited)
    envelope: tuple[float, float, float, float]  # WGS84 region envelope
    cache_dir: Path
    out_dir: Path
    manifest: dict[str, Any]
    signals: dict[str, dict[str, Any]] = field(default_factory=dict)
    lc: landcover.LandCover | None = None
    net: roads.Network | None = None
    spots: list[dict[str, Any]] = field(default_factory=list)

    def sig(self, uid: str) -> dict[str, Any]:
        return self.signals.setdefault(uid, {})

    def record(self, name: str, status: str, **extra: Any) -> None:
        self.manifest["sources"].append({"name": name, "status": status, **extra})


def mem_mb() -> float:
    """Peak memory of this process so far (MB), for the run log."""
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def guarded(ctx: Context, name: str, fn: Callable[[Context], None], warning: str) -> None:
    log.info("starting %s (peak memory so far %.0f MB)", name, mem_mb())
    try:
        fn(ctx)
        log.info("finished %s (peak memory %.0f MB)", name, mem_mb())
    except Exception as e:  # an optional analysis must never sink the whole build
        log.error("%s failed: %s\n%s", name, e, traceback.format_exc())
        ctx.record(name, "failed", error=f"{type(e).__name__}: {e}")
        ctx.manifest["warnings"].append(warning)


def analysis_bounds(ctx: Context, pad: float = 1000.0) -> tuple[float, float, float, float]:
    sel = ctx.units_ea[ctx.units_ea["id"].isin(ctx.analyze_ids)]
    minx, miny, maxx, maxy = sel.total_bounds
    return minx - pad, miny - pad, maxx + pad, maxy + pad


# ------------------------------------------------------------------ land cover


def run_landcover(ctx: Context) -> None:
    lc, tried = landcover.fetch(ctx.session, analysis_bounds(ctx))
    ctx.lc = lc
    n = 0
    for uid, geom in zip(ctx.units_ea["id"], ctx.units_ea.geometry):
        if uid not in ctx.analyze_ids:
            continue
        st = landcover.unit_stats(lc, geom)
        if st:
            s = ctx.sig(uid)
            s["landcover"] = st
            s["landcover_product"] = lc.product
            n += 1
    ctx.record(landcover.SOURCE, "ok", url=lc.url, product=lc.product, data_year=lc.year, units=n, tried=tried)
    write_landcover_overlay(ctx, lc)


def write_landcover_overlay(ctx: Context, lc: landcover.LandCover, max_px: int = 4096) -> None:
    """Color land cover image for the map, warped to Web Mercator (what MapLibre draws)."""
    from PIL import Image
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    h, w = lc.data.shape
    left, bottom, right, top = lc.bounds
    dst_tr, dw, dh = calculate_default_transform(lc.crs, "EPSG:3857", w, h, left, bottom, right, top)
    scale = max(dw / max_px, dh / max_px, 1.0)
    dw, dh = int(dw / scale), int(dh / scale)
    dst_tr, _, _ = calculate_default_transform(lc.crs, "EPSG:3857", w, h, left, bottom, right, top, dst_width=dw, dst_height=dh)
    dst = np.zeros((dh, dw), dtype=np.uint8)
    reproject(lc.data, dst, src_transform=lc.transform, src_crs=lc.crs, dst_transform=dst_tr, dst_crs="EPSG:3857", resampling=Resampling.nearest)
    rgba = landcover.to_rgba(landcover.LandCover(dst, dst_tr, "EPSG:3857", lc.product, lc.year, lc.url))
    Image.fromarray(rgba, "RGBA").save(ctx.out_dir / "landcover.png", optimize=True)
    to_ll = Transformer.from_crs("EPSG:3857", WGS84, always_xy=True)
    x0, y0 = dst_tr @ (0, 0)
    x1, y1 = dst_tr @ (dw, dh)
    (lon0, lat0), (lon1, lat1) = to_ll.transform(x0, y0), to_ll.transform(x1, y1)
    meta = {
        "product": lc.product,
        "year": lc.year,
        "coordinates": [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1]],  # TL, TR, BR, BL
        "legend": [{"code": c, "label": landcover.CLASSES[c], "rgb": landcover.COLORS[c]} for c in landcover.CLASSES],
    }
    (ctx.out_dir / "landcover.json").write_text(json.dumps(meta))


# ------------------------------------------------------------------ roads and trails


def run_roads(ctx: Context) -> None:
    import time

    frames = []
    t0 = time.time()
    try:
        dot, res = roads.fetch_dot_roads(ctx.session, ctx.envelope)
        frames.append(dot)
        ctx.record(roads.SOURCE_DOT, "ok", url=res.url, features=len(res.features), retrieved_at=res.retrieved_at)
        log.info("DOT roads: %d segments in %.0fs", len(dot), time.time() - t0)
    except Exception as e:
        ctx.record(roads.SOURCE_DOT, "failed", error=str(e))
        log.error("DOT roads failed: %s", e)
    t0 = time.time()
    try:
        osm, url = roads.fetch_osm_roads(ctx.session, ctx.envelope)
        frames.append(osm[["name", "source", "gated", "geometry"]])
        ctx.record(roads.SOURCE_OSM, "ok", url=url, features=len(osm), license="ODbL (c) OpenStreetMap contributors")
        log.info("OpenStreetMap: %d ways in %.0fs", len(osm), time.time() - t0)
    except Exception as e:
        ctx.record(roads.SOURCE_OSM, "failed", error=str(e))
        ctx.manifest["warnings"].append("OpenStreetMap logging roads unavailable; access may be underestimated in big woods.")
        log.error("OpenStreetMap failed after %.0fs: %s", time.time() - t0, e)
    if not frames:
        raise RuntimeError("no road source available")
    t0 = time.time()
    trails = None
    try:
        trails, results = roads.fetch_trails(ctx.session, ctx.envelope)
        ctx.record(roads.SOURCE_TRAILS, "ok", features=len(trails), url=roads.TRAILS_SERVICE)
        log.info("trails: %d lines in %.0fs", len(trails), time.time() - t0)
    except Exception as e:
        ctx.record(roads.SOURCE_TRAILS, "failed", error=str(e))
        log.error("trails failed: %s", e)
    t0 = time.time()
    all_roads = gpd.GeoDataFrame(gpd.pd.concat(frames, ignore_index=True), geometry="geometry", crs=WGS84)
    ctx.net = roads.Network.build(all_roads, trails)
    ctx.net.build_distance_grid(analysis_bounds(ctx))
    log.info("road network indexed and distance grid built in %.0fs (peak memory %.0f MB)", time.time() - t0, mem_mb())
    n = 0
    for uid, geom in zip(ctx.units_ea["id"], ctx.units_ea.geometry):
        if uid in ctx.analyze_ids:
            ctx.sig(uid).update(roads.unit_signals(ctx.net, geom))
            n += 1
    log.info("road signals for %d units in %.0fs", n, time.time() - t0)


# ------------------------------------------------------------------ terrain and spots


def run_terrain(ctx: Context) -> None:
    """Fixed-size elevation tiles (core + margin). Units crossing tiles gather samples from each."""
    sel = ctx.units_ea[ctx.units_ea["id"].isin(ctx.analyze_ids)].reset_index(drop=True)
    tree = shapely.STRtree(list(sel.geometry.values))
    tiles = terrain.tile_grid(analysis_bounds(ctx, pad=0), TILE_M)
    dem_cache = ctx.cache_dir / "dem"
    margin = 600.0
    samples: dict[int, list[dict[str, Any]]] = {}
    feats_by_unit: dict[int, list[terrain.Feature]] = {}
    n_tiles = 0
    for core in tiles:
        core_box = shapely.box(*core)
        hits = tree.query(core_box, predicate="intersects")
        if len(hits) == 0:
            continue
        b = (core[0] - margin, core[1] - margin, core[2] + margin, core[3] + margin)
        dem = terrain.fetch_dem(ctx.session, b, res_m=DEM_RES_M, cache_dir=dem_cache)
        layers = terrain.derive(dem)
        feats = [f for f in terrain.find_features(dem, layers) if core[0] <= f.x < core[2] and core[1] <= f.y < core[3]]
        for j in hits:
            part = terrain.unit_samples(dem, layers, sel.geometry.iloc[int(j)], core=core)
            if part:
                samples.setdefault(int(j), []).append(part)
        for f in feats:
            for j in tree.query(shapely.Point(f.x, f.y), predicate="within"):
                feats_by_unit.setdefault(int(j), []).append(f)
        n_tiles += 1
        del dem, layers
        log.info("terrain tile %d: %d units, %d features, peak memory %.0f MB", n_tiles, len(hits), len(feats), mem_mb())

    feature_counts = {"saddle": 0, "bench": 0}
    done = 0
    for j, parts in samples.items():
        stats = terrain.finalize_samples(parts, DEM_RES_M)
        if not stats:
            continue
        uid = sel.loc[j, "id"]
        fs = feats_by_unit.get(j, [])
        s = ctx.sig(uid)
        s["terrain"] = stats
        s["saddles"] = sum(f.kind == "saddle" for f in fs)
        s["benches"] = sum(f.kind == "bench" for f in fs)
        feature_counts["saddle"] += s["saddles"]
        feature_counts["bench"] += s["benches"]
        done += 1
        ctx.spots.extend(make_spots(ctx, uid, sel.loc[j, "property_id"], sel.geometry.iloc[j], fs))
    ctx.record(
        terrain.SOURCE,
        "ok",
        url=terrain.IMAGE_SERVER,
        tiles=n_tiles,
        units=done,
        resolution_m=DEM_RES_M,
        features=feature_counts,
        spots=len(ctx.spots),
    )


def make_spots(ctx: Context, uid: str, pid: str, geom, feats: list[terrain.Feature]) -> list[dict[str, Any]]:
    scored = []
    for f in feats:
        pt = shapely.Point(f.x, f.y)
        road_m = trail_m = None
        road_info = None
        if ctx.net is not None and ctx.net._dtree is not None:
            k = int(ctx.net._dtree.nearest(pt))
            road = ctx.net.drivable[k]
            road_m = float(pt.distance(road))
            near = shapely.ops.nearest_points(pt, road)[1]
            name = ctx.net.drivable_names[k]
            road_info = {
                "road_name": name,
                "distance_m": round(road_m),
                "road_bearing_deg": round(spots.bearing_deg(f.x, f.y, near.x, near.y)),
            }
        if ctx.net is not None and ctx.net._ttree is not None:
            k = int(ctx.net._ttree.nearest(pt))
            trail_m = float(pt.distance(ctx.net.trails[k]))
        score, conf, why = spots.score_spot(
            f,
            edge_m=spots.edge_distance_m(ctx.lc, f.x, f.y),
            cover_class=spots.cover_at(ctx.lc, f.x, f.y),
            road_m=road_m,
            trail_m=trail_m,
            boundary_m=float(geom.boundary.distance(pt)),
        )
        scored.append((score, f, conf, why, road_info))
    scored.sort(key=lambda t: -t[0])
    kept: list[tuple] = []
    for item in scored:
        f = item[1]
        if all(math.hypot(f.x - k[1].x, f.y - k[1].y) >= SPOT_MIN_SPACING_M for k in kept):
            kept.append(item)
        if len(kept) >= SPOTS_PER_UNIT:
            break
    out = []
    for score, f, conf, why, road_info in kept:
        lon, lat = _TO_WGS.transform(f.x, f.y)
        out.append(spots.spot_record(f, uid, pid, (lon, lat), score, conf, why, road_info))
    return out


# ------------------------------------------------------------------ wind history


def run_wind_history(ctx: Context, step_deg: float = 0.25, max_points: int = 16) -> None:
    sel = ctx.units_ea[ctx.units_ea["id"].isin(ctx.analyze_ids)]
    reps = gpd.GeoSeries(sel.geometry.representative_point(), crs=EQUAL_AREA).to_crs(WGS84)
    cells: dict[str, tuple[float, float]] = {}
    for p in reps:
        lat = round(round(p.y / step_deg) * step_deg, 2)
        lon = round(round(p.x / step_deg) * step_deg, 2)
        cells.setdefault(f"{lat:.2f},{lon:.2f}", (lat, lon))
    pts = [(k, la, lo) for k, (la, lo) in list(cells.items())[:max_points]]
    hist = windhistory.history(ctx.session, pts)
    hist["cell_step_deg"] = step_deg
    (ctx.out_dir / "wind_history.json").write_text(json.dumps(hist, separators=(",", ":")))
    ctx.record(windhistory.SOURCE, "ok", url=windhistory.ARCHIVE, points=len(pts), period=hist["period"], license="CC BY 4.0")


def run_all(ctx: Context, skip: set[str] = frozenset()) -> None:
    if "landcover" not in skip:
        guarded(ctx, landcover.SOURCE, run_landcover, "Land cover unavailable; habitat isn't scored this run.")
    if "roads" not in skip:
        guarded(ctx, "Roads and trails", run_roads, "Roads unavailable; access and pressure aren't scored this run.")
    if "terrain" not in skip:
        guarded(ctx, terrain.SOURCE, run_terrain, "Elevation data unavailable; terrain and spots aren't scored this run.")
    if "wind" not in skip:
        guarded(ctx, windhistory.SOURCE, run_wind_history, "Historical wind unavailable this run.")
