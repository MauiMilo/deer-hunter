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


def fetch_dem(
    session: Session,
    bounds_5070: tuple[float, float, float, float],
    res_m: float = 5.0,
    cache_dir: Path | None = None,
) -> Dem:
    minx, miny, maxx, maxy = bounds_5070
    w = int(round((maxx - minx) / res_m))
    h = int(round((maxy - miny) / res_m))
    if w > 8000 or h > 8000:
        raise ValueError("tile too large for the elevation service (8000 px max)")
    key = hashlib.sha1(f"{bounds_5070}|{res_m}".encode()).hexdigest()[:16]
    cached = cache_dir / f"dem_{key}.tif" if cache_dir else None
    if cached and cached.exists():
        body = cached.read_bytes()
    else:
        params = {
            "bbox": f"{minx},{miny},{maxx},{maxy}",
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
        body, ctype = get_bytes(session, IMAGE_SERVER, params, source=SOURCE, timeout=300, max_bytes=8 * w * h + 1_000_000)
        if body[:4] not in (b"II*\x00", b"MM\x00*"):
            raise SourceError(SOURCE, f"expected a TIFF, got {ctype}: {body[:200]!r}")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(body)
    with rasterio.io.MemoryFile(io.BytesIO(body)) as mf, mf.open() as ds:
        z = ds.read(1).astype(np.float32)
        nd = ds.nodata
    z[(z <= -1000) | (z > 9000)] = np.nan
    if nd is not None:
        z[z == nd] = np.nan
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
    return TerrainLayers(slope, aspect, tpi_s, tpi_l, det, bearing, r)


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
        idx = np.arange(1, n + 1)
        counts = ndimage.sum(mask, lab, idx)
        for k, cnt in zip(idx, counts):
            area = float(cnt) * r * r
            if area < min_m2:
                continue
            rows, cols = np.nonzero(lab == k)
            if kind == "saddle":
                pick = np.argmin(t.hess_det[rows, cols])
            else:
                pick = np.argmin(t.slope_deg[rows, cols])
            rr, cc = int(rows[pick]), int(cols[pick])
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
