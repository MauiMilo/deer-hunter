"""Terrain from USGS 3DEP bare-earth elevation (LiDAR-derived where available), and candidate
movement features: saddles, benches, ridges and valleys.

Elevation is requested from the 3DEP ImageServer at a few meters per pixel, tile by tile, only
where there are blocks to analyze. Everything here is "candidate" terrain: a saddle or bench is a
shape in the ground, not proof deer use it. Bare-earth elevation says nothing about vegetation
or understory.
"""

from __future__ import annotations

import hashlib
import io
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.transform import Affine, from_origin
from scipy import ndimage

from .http import Session, SourceError, get_bytes

SOURCE = "USGS 3DEP elevation"
IMAGE_SERVER = "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
# 1/3 arc-second (~10 m) seamless 3DEP DEM as cloud-optimized GeoTIFFs on USGS's public S3 bucket,
# one file per 1-degree cell named by its north-west corner (e.g. n46w072 covers 45-46 N, 72-71 W).
COG_TEMPLATE = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/{tile}/USGS_13_{tile}.tif"
NODATA = -9999.0


@dataclass
class Dem:
    z: np.ndarray  # float32 meters, NaN for no data
    transform: Affine
    res: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        h, w = self.z.shape
        minx, maxy = self.transform @ (0, 0)
        maxx, miny = self.transform @ (w, h)
        return minx, miny, maxx, maxy


def tile_grid(bounds, tile_m: float) -> list[tuple[float, float, float, float]]:
    minx, miny, maxx, maxy = bounds
    x0 = math.floor(minx / tile_m) * tile_m
    y0 = math.floor(miny / tile_m) * tile_m
    out = []
    y = y0
    while y < maxy:
        x = x0
        while x < maxx:
            out.append((x, y, x + tile_m, y + tile_m))
            x += tile_m
        y += tile_m
    return out


def _fetch_chunk(session: Session, b: tuple[float, float, float, float], w: int, h: int) -> np.ndarray:
    params = {
        "bbox": f"{b[0]},{b[1]},{b[2]},{b[3]}",
        "bboxSR": 5070,
        "imageSR": 5070,
        "size": f"{w},{h}",
        "format": "tiff",
        "pixelType": "F32",
        "noData": NODATA,
        "noDataInterpretation": "esriNoDataMatchAny",
        "interpolation": "RSP_BilinearInterpolation",
        "renderingRule": '{"rasterFunction":"None"}',
        "f": "image",
    }
    # The elevation service sometimes answers 502/503 under load; back off and retry patiently.
    body, ctype = get_bytes(
        session, IMAGE_SERVER, params, source=SOURCE, timeout=180, retries=5, backoff=5.0, max_bytes=8 * w * h + 1_000_000
    )
    if body[:4] not in (b"II*\x00", b"MM\x00*"):
        raise SourceError(SOURCE, f"expected a TIFF, got {ctype}: {body[:200]!r}")
    with rasterio.io.MemoryFile(io.BytesIO(body)) as mf, mf.open() as ds:
        arr = ds.read(1).astype(np.float32)
        nd = ds.nodata
    if arr.shape != (h, w):
        raise SourceError(SOURCE, f"expected {w}x{h} pixels, got {arr.shape[1]}x{arr.shape[0]}")
    if nd is not None:
        arr[arr == nd] = np.nan
    return arr


def cog_tile_names(bounds_wgs: tuple[float, float, float, float]) -> list[str]:
    """1-degree 3DEP tile names covering a lon/lat box."""
    w, south, e, n = bounds_wgs
    names = []
    for north in range(math.floor(south) + 1, math.ceil(n) + 1):
        for west in range(math.ceil(-e), math.ceil(-w) + 1):
            if west <= 0:
                continue
            names.append(f"n{north:02d}w{west:03d}")
    return sorted(set(names))


def fetch_dem_cog(
    bounds_5070: tuple[float, float, float, float],
    res_m: float = 10.0,
    template: str = COG_TEMPLATE,
    cache_dir: Path | None = None,
) -> Dem:
    """Elevation for a box from the 3DEP 1/3 arc-second cloud-optimized GeoTIFFs.

    GDAL reads only the parts of each 1-degree file the box needs (HTTP range requests),
    then warps them onto our equal-area grid.
    """
    from pyproj import Transformer
    from rasterio.warp import Resampling, reproject

    minx, miny, maxx, maxy = bounds_5070
    w = int(round((maxx - minx) / res_m))
    h = int(round((maxy - miny) / res_m))
    key = hashlib.sha1(f"cog|{bounds_5070}|{res_m}".encode()).hexdigest()[:16]
    cached = cache_dir / f"dem_{key}.npy" if cache_dir else None
    if cached and cached.exists():
        z = np.load(cached)
    else:
        to_ll = Transformer.from_crs("EPSG:5070", "EPSG:4269", always_xy=True)
        xs, ys = to_ll.transform([minx, maxx, minx, maxx], [miny, miny, maxy, maxy])
        names = cog_tile_names((min(xs), min(ys), max(xs), max(ys)))
        dst_tr = from_origin(minx, maxy, res_m, res_m)
        z = np.full((h, w), np.nan, dtype=np.float32)
        env = {
            "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
            "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
            "GDAL_HTTP_MAX_RETRY": "4",
            "GDAL_HTTP_RETRY_DELAY": "3",
            "VSI_CACHE": "TRUE",
        }
        got = 0
        with rasterio.Env(**env):
            for name in names:
                url = template.format(tile=name)
                path = url if not url.startswith("http") else f"/vsicurl/{url}"
                try:
                    with rasterio.open(path) as src:
                        part = np.full((h, w), np.nan, dtype=np.float32)
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=part,
                            src_nodata=src.nodata,
                            dst_transform=dst_tr,
                            dst_crs="EPSG:5070",
                            dst_nodata=np.nan,
                            resampling=Resampling.bilinear,
                        )
                except rasterio.errors.RasterioIOError as e:
                    raise SourceError(SOURCE, f"couldn't read {url}: {e}") from e
                fill = np.isnan(z) & ~np.isnan(part)
                z[fill] = part[fill]
                got += 1
        if got == 0:
            raise SourceError(SOURCE, "no elevation tiles cover this area")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            np.save(cached, z)
    z = z.copy()
    z[(z <= -1000) | (z > 9000)] = np.nan
    if np.isnan(z).mean() > 0.5:
        raise SourceError(SOURCE, "elevation tile is mostly empty")
    return Dem(z, from_origin(minx, maxy, res_m, res_m), res_m)


def fetch_dem(
    session: Session,
    bounds_5070: tuple[float, float, float, float],
    res_m: float = 5.0,
    cache_dir: Path | None = None,
    chunk_px: int = 800,
) -> Dem:
    """Elevation for a box, requested in chunks of at most chunk_px square and stitched together."""
    minx, miny, maxx, maxy = bounds_5070
    w = int(round((maxx - minx) / res_m))
    h = int(round((maxy - miny) / res_m))
    if w > 8000 or h > 8000:
        raise ValueError("tile too large for the elevation service (8000 px max)")
    key = hashlib.sha1(f"{bounds_5070}|{res_m}".encode()).hexdigest()[:16]
    cached = cache_dir / f"dem_{key}.npy" if cache_dir else None
    if cached and cached.exists():
        z = np.load(cached)
    else:
        z = np.full((h, w), np.nan, dtype=np.float32)
        for r0 in range(0, h, chunk_px):
            for c0 in range(0, w, chunk_px):
                hh, ww = min(chunk_px, h - r0), min(chunk_px, w - c0)
                cb = (minx + c0 * res_m, maxy - (r0 + hh) * res_m, minx + (c0 + ww) * res_m, maxy - r0 * res_m)
                z[r0 : r0 + hh, c0 : c0 + ww] = _fetch_chunk(session, cb, ww, hh)
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            np.save(cached, z)
    z = z.copy()
    z[(z <= -1000) | (z > 9000)] = np.nan
    if np.isnan(z).mean() > 0.5:
        raise SourceError(SOURCE, "elevation tile is mostly empty")
    return Dem(z, from_origin(minx, maxy, res_m, res_m), res_m)


# ---------------------------------------------------------------- derivatives


def _fill(z: np.ndarray) -> np.ndarray:
    """Replace NaN with the nearest valid value so filters don't smear holes."""
    if not np.isnan(z).any():
        return z
    idx = ndimage.distance_transform_edt(np.isnan(z), return_distances=False, return_indices=True)
    return z[tuple(idx)]


def _mean_disk(z: np.ndarray, radius_px: int) -> np.ndarray:
    return ndimage.uniform_filter(z, size=2 * radius_px + 1, mode="nearest")


@dataclass
class TerrainLayers:
    slope_deg: np.ndarray
    aspect_deg: np.ndarray  # downslope direction, degrees clockwise from north
    tpi_small: np.ndarray  # m above the local (~50 m) mean
    tpi_large: np.ndarray  # m above the landscape (~300 m) mean
    hess_det: np.ndarray  # determinant of the elevation surface's curvature (negative = saddle-shaped)
    ridge_axis_deg: np.ndarray  # direction of upward curvature at each cell
    res: float
    z_smooth: np.ndarray | None = None  # lightly smoothed elevation, for prominence checks


def derive(dem: Dem, smooth_m: float = 10.0) -> TerrainLayers:
    r = dem.res
    z = _fill(dem.z.astype(np.float32))
    zs = ndimage.gaussian_filter(z, sigma=max(0.5, smooth_m / r))
    dzdy, dzdx = np.gradient(zs, r)  # rows increase southward
    dzdn = -dzdy  # northward gradient
    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdn)))
    aspect = (np.degrees(np.arctan2(-dzdx, -dzdn)) + 360) % 360  # direction of steepest descent

    tpi_s = z - _mean_disk(z, max(1, int(50 / r)))
    tpi_l = z - _mean_disk(z, max(2, int(300 / r)))

    # Curvature at ~30 m scale for saddle detection. Rows run south, columns east.
    zc = ndimage.gaussian_filter(z, sigma=max(1.0, 30.0 / r))
    g_s, g_e = np.gradient(zc, r)
    f_ss, f_se = np.gradient(g_s, r)
    _, f_ee = np.gradient(g_e, r)
    f_nn, f_en = f_ss, -f_se  # flip to north-up axes
    det = f_ee * f_nn - f_en**2  # < 0 where the ground curves up one way and down the other (a saddle)
    # Direction of the strongest upward curvature (the ridge line at a saddle), from east, counterclockwise.
    theta = 0.5 * np.arctan2(2 * f_en, f_ee - f_nn)
    lam_theta = f_ee * np.cos(theta) ** 2 + 2 * f_en * np.sin(theta) * np.cos(theta) + f_nn * np.sin(theta) ** 2
    lam1 = (f_ee + f_nn) / 2 + np.sqrt(((f_ee - f_nn) / 2) ** 2 + f_en**2)
    theta = np.where(np.isclose(lam_theta, lam1, rtol=1e-6, atol=1e-12), theta, theta + np.pi / 2)
    bearing = (90 - np.degrees(theta)) % 180  # compass axis, 0-180
    nan = np.isnan(dem.z)
    for arr in (slope, aspect, tpi_s, tpi_l, det, bearing):
        arr[nan] = np.nan
    return TerrainLayers(slope, aspect, tpi_s, tpi_l, det, bearing, r, zs.astype(np.float32))


# ---------------------------------------------------------------- features


@dataclass
class Feature:
    kind: str  # "saddle" | "bench"
    x: float
    y: float
    elevation_m: float
    slope_deg: float
    area_m2: float
    travel_axis_deg: float  # likely direction of travel through/along the feature (0-180)
    notes: list[str] = field(default_factory=list)


SADDLE_PROMINENCE_M = 6.0  # ground must rise this much along the ridge and fall across it, both ways
SADDLE_REACH_M = 150.0
BENCH_STEP_M = 10.0  # a bench must have this much climb above and drop below it
BENCH_REACH_M = 100.0


def _rise(z: np.ndarray, r: int, c: int, bearing_deg: float, dist_m: float, res: float) -> float | None:
    """Elevation change from (r, c) to the point dist_m away on a compass bearing (NaN-safe)."""
    b = math.radians(bearing_deg)
    dc = math.sin(b) * dist_m / res
    dr = -math.cos(b) * dist_m / res
    rr, cc = int(round(r + dr)), int(round(c + dc))
    if not (0 <= rr < z.shape[0] and 0 <= cc < z.shape[1]):
        return None
    v = z[rr, cc] - z[r, c]
    return None if np.isnan(v) else float(v)


def is_prominent_saddle(z: np.ndarray, r: int, c: int, ridge_axis_deg: float, res: float) -> bool:
    along = [_rise(z, r, c, ridge_axis_deg + k, SADDLE_REACH_M, res) for k in (0, 180)]
    across = [_rise(z, r, c, ridge_axis_deg + k, SADDLE_REACH_M, res) for k in (90, 270)]
    if any(v is None for v in along + across):
        return False
    return min(along) >= SADDLE_PROMINENCE_M and max(across) <= -SADDLE_PROMINENCE_M


def is_true_bench(z: np.ndarray, r: int, c: int, downslope_deg: float, res: float) -> bool:
    down = _rise(z, r, c, downslope_deg, BENCH_REACH_M, res)
    up = _rise(z, r, c, downslope_deg + 180, BENCH_REACH_M, res)
    if down is None or up is None:
        return False
    return down <= -BENCH_STEP_M and up >= BENCH_STEP_M


def find_features(dem: Dem, t: TerrainLayers) -> list[Feature]:
    r = dem.res
    feats: list[Feature] = []
    valid = ~np.isnan(t.slope_deg)
    sd_l = np.nanstd(t.tpi_large) or 1.0

    # Saddles: low point between two higher points along a ridge line (negative curvature
    # determinant, gentle slope, and higher than the surrounding landscape).
    saddle = valid & (t.hess_det < -2e-6) & (t.slope_deg < 12) & (t.tpi_large > 0.25 * sd_l)
    # Benches: flat shelves partway up a hillside.
    local_slope = ndimage.uniform_filter(np.nan_to_num(t.slope_deg), size=max(3, int(2 * 60 / r) + 1))
    bench = valid & (t.slope_deg < 8) & (local_slope > 16) & (np.abs(t.tpi_large) < 0.6 * sd_l)

    for kind, mask, min_m2 in (("saddle", saddle, 600.0), ("bench", bench, 1500.0)):
        lab, n = ndimage.label(mask)
        if n == 0:
            continue
        for k, sl in enumerate(ndimage.find_objects(lab), start=1):
            if sl is None:
                continue
            sub = lab[sl] == k
            area = float(sub.sum()) * r * r
            if area < min_m2:
                continue
            rows, cols = np.nonzero(sub)
            rows = rows + sl[0].start
            cols = cols + sl[1].start
            if kind == "saddle":
                pick = np.argmin(t.hess_det[rows, cols])
            else:
                pick = np.argmin(t.slope_deg[rows, cols])
            rr, cc = int(rows[pick]), int(cols[pick])
            zs = t.z_smooth if t.z_smooth is not None else dem.z
            if kind == "saddle" and not is_prominent_saddle(zs, rr, cc, float(t.ridge_axis_deg[rr, cc]), r):
                continue
            if kind == "bench" and not is_true_bench(zs, rr, cc, float(np.nanmedian(t.aspect_deg[rows, cols])), r):
                continue
            x, y = dem.transform @ (cc + 0.5, rr + 0.5)
            if kind == "saddle":
                axis = (float(t.ridge_axis_deg[rr, cc]) + 90.0) % 180.0  # travel crosses the ridge
                notes = ["Low point on a ridge line; deer often cross ridges at saddles."]
            else:
                axis = (float(np.nanmedian(t.aspect_deg[rows, cols])) + 90.0) % 180.0  # along the contour
                notes = ["Flat shelf on a slope; deer often travel and bed along benches."]
            feats.append(
                Feature(kind, float(x), float(y), float(dem.z[rr, cc]), float(t.slope_deg[rr, cc]), area, round(axis, 1), notes)
            )
    return feats


def unit_samples(dem: Dem, t: TerrainLayers, geom_5070, core: tuple[float, float, float, float] | None = None) -> dict[str, np.ndarray] | None:
    """Pixel values of a unit inside this tile (optionally only inside the tile's core area).

    Units that cross tiles collect samples from each tile; `finalize_samples` turns them into stats.
    """
    g = geom_5070
    if core is not None:
        from shapely.geometry import box

        g = g.intersection(box(*core))
        if g.is_empty:
            return None
    minx, miny, maxx, maxy = g.bounds
    bx = dem.bounds
    minx, miny, maxx, maxy = max(minx, bx[0]), max(miny, bx[1]), min(maxx, bx[2]), min(maxy, bx[3])
    if minx >= maxx or miny >= maxy:
        return None
    inv = ~dem.transform
    c0, r0 = inv @ (minx, maxy)
    c1, r1 = inv @ (maxx, miny)
    r0, c0 = max(0, int(r0)), max(0, int(c0))
    r1 = min(dem.z.shape[0], int(math.ceil(r1)))
    c1 = min(dem.z.shape[1], int(math.ceil(c1)))
    if r1 <= r0 or c1 <= c0:
        return None
    sl = (slice(r0, r1), slice(c0, c1))
    tr = dem.transform @ Affine.translation(c0, r0)
    inside = geometry_mask([g], out_shape=dem.z[sl].shape, transform=tr, invert=True)
    if not inside.any():
        return None
    sd_l = float(np.nanstd(t.tpi_large) or 1.0)
    return {
        "z": dem.z[sl][inside].astype(np.float32),
        "slope": t.slope_deg[sl][inside].astype(np.float32),
        "tpi_rel": (t.tpi_large[sl][inside] / sd_l).astype(np.float32),
    }


def finalize_samples(parts: list[dict[str, np.ndarray]], res: float) -> dict[str, Any] | None:
    if not parts:
        return None
    z = np.concatenate([p["z"] for p in parts])
    s = np.concatenate([p["slope"] for p in parts])
    tl = np.concatenate([p["tpi_rel"] for p in parts])
    if z.size < 20 or np.isnan(z).mean() > 0.3:
        return None
    return {
        "dem_res_m": res,
        "elev_min_m": round(float(np.nanmin(z)), 1),
        "elev_max_m": round(float(np.nanmax(z)), 1),
        "relief_m": round(float(np.nanpercentile(z, 95) - np.nanpercentile(z, 5)), 1),
        "mean_slope_deg": round(float(np.nanmean(s)), 1),
        "steep_share": round(float(np.nanmean(s > 30)), 4),
        "gentle_share": round(float(np.nanmean(s < 8)), 4),
        "ridge_share": round(float(np.nanmean(tl > 1)), 4),
        "valley_share": round(float(np.nanmean(tl < -1)), 4),
    }


def unit_signals(dem: Dem, t: TerrainLayers, geom_5070) -> dict[str, Any] | None:
    """Stats for a unit that lies within one tile (convenience wrapper)."""
    minx, miny, maxx, maxy = geom_5070.bounds
    bx = dem.bounds
    if minx < bx[0] or miny < bx[1] or maxx > bx[2] or maxy > bx[3]:
        return None
    part = unit_samples(dem, t, geom_5070)
    return finalize_samples([part] if part else [], dem.res)
