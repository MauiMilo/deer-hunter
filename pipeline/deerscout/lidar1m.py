"""Check scouting spots against the USGS 1-meter lidar elevation, where it exists.

The county-wide terrain search runs on the 10 m seamless elevation model: it covers everything
and runs in minutes, but 10 m smooths over small shelves and can mistake a pond shore for a
saddle. This step re-reads a small window (about 240 m across) of the 1 m lidar model around
each candidate spot and asks plain questions:

  bench   Is the ground actually flat here? If not, is there a flat shelf within 30 m?
          (If so the spot moves there.)
  saddle  Does the ground rise both ways along one line and fall both ways across it?
  water   Is the spot on or beside a water surface? (Lidar elevation is flattened over
          water, which fools the 10 m search.) Those spots are dropped.

Where no 1 m lidar covers a spot, it is labeled "not checked at 1 m" and left as is.
The 1 m tiles are listed through The National Map's product API and read in small pieces
straight from USGS's public S3 bucket (cloud-optimized GeoTIFFs); nothing is downloaded whole.
"""

from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from scipy import ndimage

from .http import Session, get_json

log = logging.getLogger(__name__)

SOURCE = "USGS 3DEP 1 m lidar (spot check)"
TNM_PRODUCTS = "https://tnmaccess.nationalmap.gov/api/v1/products"
DATASET = "Digital Elevation Model (DEM) 1 meter"

HALF_WINDOW_M = 120.0
BENCH_OK_DEG = 10.0  # average slope within 10 m that counts as a real shelf
BENCH_MOVE_DEG = 8.0  # a better shelf nearby must be at least this flat
BENCH_SEARCH_M = 30.0
SADDLE_MIN_M = 2.0  # rise along the ridge and fall across it, each way
WATER_FLAT_PX = 300  # a perfectly level patch this big (m² at 1 m) is a water surface
WATER_NEAR_M = 35.0
WATER_NEAR_LEVEL = 0.004  # m per m: under a quarter of a degree
WATER_NEAR_LEVEL_M2 = 1500.0
NOT_CONFIRMED_PENALTY = 15


@dataclass(frozen=True)
class Tile:
    url: str
    project: str
    published: str
    bbox: tuple[float, float, float, float]  # lon/lat: minx, miny, maxx, maxy

    def covers(self, lon: float, lat: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        return x0 <= lon <= x1 and y0 <= lat <= y1


@dataclass
class Check:
    verdict: str  # confirmed | moved | not_confirmed | water
    detail: str
    dx_m: float = 0.0  # move east (m)
    dy_m: float = 0.0  # move north (m)
    travel_axis_deg: float | None = None


# ------------------------------------------------------------------ finding tiles


def parse_products(doc: dict[str, Any]) -> list[Tile]:
    out = []
    for it in doc.get("items", []):
        url = it.get("downloadURL") or ""
        bb = it.get("boundingBox") or {}
        if not url.lower().endswith(".tif") or not bb:
            continue
        project = url.split("/Projects/")[1].split("/")[0] if "/Projects/" in url else ""
        out.append(Tile(url, project, str(it.get("publicationDate") or ""), (bb["minX"], bb["minY"], bb["maxX"], bb["maxY"])))
    return out


def find_tiles(session: Session, envelope: tuple[float, float, float, float], page: int = 500) -> list[Tile]:
    w, s, e, n = envelope
    tiles: list[Tile] = []
    offset = 0
    while True:
        doc = get_json(
            session,
            TNM_PRODUCTS,
            {"datasets": DATASET, "bbox": f"{w},{s},{e},{n}", "max": page, "offset": offset, "outputFormat": "JSON"},
            source=SOURCE,
            timeout=90,
        )
        batch = parse_products(doc)
        tiles.extend(batch)
        offset += page
        if offset >= int(doc.get("total") or 0) or not doc.get("items"):
            break
    return tiles


def tiles_for(tiles: Iterable[Tile], lon: float, lat: float) -> list[Tile]:
    """Tiles covering a point, newest first."""
    return sorted((t for t in tiles if t.covers(lon, lat)), key=lambda t: (t.published, t.project), reverse=True)


# ------------------------------------------------------------------ checks (pure functions)


def _slope_deg(z: np.ndarray, res: float, sigma_m: float) -> np.ndarray:
    zs = ndimage.gaussian_filter(z, sigma_m / res)
    gy, gx = np.gradient(zs, res)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def _disk(radius_px: int) -> np.ndarray:
    yy, xx = np.mgrid[-radius_px : radius_px + 1, -radius_px : radius_px + 1]
    return (xx * xx + yy * yy) <= radius_px * radius_px


def near_water(z: np.ndarray, res: float) -> bool:
    """A water surface near the center. Lidar models flatten water: either one exact elevation, or
    (in some projects) a nearly dead-level surface with tiny noise. Dry ground, even a hayfield,
    has more relief than that over this much area."""
    gy, gx = np.gradient(z, res)
    finite = np.isfinite(z)
    c = z.shape[0] // 2
    for tol, min_m2 in ((1e-4, WATER_FLAT_PX), (WATER_NEAR_LEVEL, WATER_NEAR_LEVEL_M2)):
        level = (np.abs(gx) < tol) & (np.abs(gy) < tol) & finite
        lab, n = ndimage.label(level)
        if n == 0:
            continue
        sizes = ndimage.sum(level, lab, index=np.arange(1, n + 1))
        big = np.isin(lab, np.nonzero(sizes * res * res >= min_m2)[0] + 1)
        if big.any() and ndimage.distance_transform_edt(~big)[c, c] * res <= WATER_NEAR_M:
            return True
    return False


def check_bench(z: np.ndarray, res: float) -> Check:
    slope = _slope_deg(z, res, 2.0)
    c = z.shape[0] // 2
    r10 = int(round(10 / res))
    disk = _disk(r10)
    win = slope[c - r10 : c + r10 + 1, c - r10 : c + r10 + 1]
    here = float(np.nanmean(win[disk]))
    if here <= BENCH_OK_DEG:
        flat = slope < BENCH_OK_DEG
        lab, _ = ndimage.label(flat)
        area = float((lab == lab[c, c]).sum() * res * res) if flat[c, c] else 0.0
        size = f", about {area / 4046.86:.1f} acres of flat ground" if area >= 200 else ""
        return Check("confirmed", f"1 m lidar confirms a flat shelf here (average slope {here:.0f}° within 10 m{size}).")
    # Look for a real shelf nearby: average slope in an 8 m circle, lowest within 30 m.
    k = _disk(int(round(8 / res))).astype(float)
    mean = ndimage.convolve(np.nan_to_num(slope, nan=90.0), k / k.sum(), mode="nearest")
    rs = int(round(BENCH_SEARCH_M / res))
    sub = mean[c - rs : c + rs + 1, c - rs : c + rs + 1].copy()
    sub[~_disk(rs)] = np.inf
    best = float(np.min(sub))
    # Of the places nearly as flat as the flattest, take the closest: don't move farther than needed.
    yy, xx = np.mgrid[-rs : rs + 1, -rs : rs + 1]
    near_best = np.where(sub <= best + 1.0, np.hypot(xx, yy), np.inf)
    i, j = np.unravel_index(int(np.argmin(near_best)), sub.shape)
    best = float(sub[i, j])
    if best <= BENCH_MOVE_DEG:
        dx = (j - rs) * res
        dy = -(i - rs) * res
        d = math.hypot(dx, dy)
        return Check("moved", f"Moved {d:.0f} m to the flat shelf the 1 m lidar shows (average slope {best:.0f}°).", dx, dy)
    return Check("not_confirmed", f"At 1 m detail the ground here averages {here:.0f}°, with no flat shelf within 30 m.")


def _sample(z: np.ndarray, r: float, c: float) -> float:
    return float(ndimage.map_coordinates(z, [[r], [c]], order=1, mode="nearest")[0])


def check_saddle(z: np.ndarray, res: float) -> Check:
    zs = ndimage.gaussian_filter(z, 4.0 / res)
    c = (z.shape[0] - 1) / 2
    z0 = _sample(zs, c, c)
    best = (-np.inf, 0.0, 0.0, 0.0)  # (strength, ridge bearing, rise, fall)
    for theta in range(0, 180, 15):
        t = math.radians(theta)
        u = math.radians(theta + 90)
        for dist in (40.0, 70.0):
            k = dist / res
            ridge = [
                _sample(zs, c - math.cos(t) * k * s, c + math.sin(t) * k * s) - z0 for s in (1, -1)
            ]
            across = [
                z0 - _sample(zs, c - math.cos(u) * k * s, c + math.sin(u) * k * s) for s in (1, -1)
            ]
            rise, fall = min(ridge), min(across)
            strength = min(rise, fall)
            if strength > best[0]:
                best = (strength, float(theta), rise, fall)
    strength, ridge_deg, rise, fall = best
    if strength >= SADDLE_MIN_M:
        return Check(
            "confirmed",
            f"1 m lidar confirms the saddle: ground rises {rise:.0f} m each way along the ridge and drops {fall:.0f} m each way across it.",
            travel_axis_deg=(ridge_deg + 90) % 180,
        )
    return Check("not_confirmed", "At 1 m detail the saddle shape is weak (less than 2 m of rise and fall around it).")


def check_window(kind: str, z: np.ndarray, res: float) -> Check:
    if near_water(z, res):
        return Check("water", "1 m lidar shows a water surface right beside this spot.")
    return check_saddle(z, res) if kind == "saddle" else check_bench(z, res)


# ------------------------------------------------------------------ reading the lidar


def _read_window(ds, lon: float, lat: float, half_m: float) -> tuple[np.ndarray, float] | None:
    import rasterio.windows
    from pyproj import Transformer

    tr = Transformer.from_crs("EPSG:4326", ds.crs, always_xy=True)
    x, y = tr.transform(lon, lat)
    res = abs(ds.res[0])
    row, col = ds.index(x, y)
    n = int(half_m / res)
    win = rasterio.windows.Window(col - n, row - n, 2 * n + 1, 2 * n + 1)
    arr = ds.read(1, window=win, boundless=True, masked=True).astype("float32")
    z = arr.filled(np.nan)
    if np.isfinite(z).mean() < 0.85:
        return None  # edge of the lidar project or missing data
    if not np.isfinite(z).all():
        z = np.where(np.isfinite(z), z, np.nanmean(z))
    return z, res


GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
}


def check_spots(spot_list: list[dict[str, Any]], tiles: list[Tile], workers: int = 8) -> dict[str, tuple[Check | None, Tile | None]]:
    """Check each spot against the newest 1 m tile that has data there.

    Returns spot id -> (check, tile). (None, None) = no 1 m lidar here.
    """
    import rasterio

    plan: dict[str, list[dict[str, Any]]] = {}
    out: dict[str, tuple[Check | None, Tile | None]] = {}
    cand: dict[str, list[Tile]] = {}
    for sp in spot_list:
        lon, lat = sp["point"]
        ts = tiles_for(tiles, lon, lat)
        if not ts:
            out[sp["id"]] = (None, None)
            continue
        cand[sp["id"]] = ts
        plan.setdefault(ts[0].url, []).append(sp)

    def run(url: str, group: list[dict[str, Any]]) -> list[tuple[str, Check | None, Tile | None]]:
        res_list = []
        with rasterio.Env(**GDAL_ENV):
            handles: dict[str, Any] = {}
            try:
                for sp in group:
                    lon, lat = sp["point"]
                    got = None
                    for t in cand[sp["id"]]:
                        try:
                            ds = handles.get(t.url) or handles.setdefault(t.url, rasterio.open("/vsicurl/" + t.url))
                            w = _read_window(ds, lon, lat, HALF_WINDOW_M)
                        except Exception as e:  # one bad tile shouldn't stop the rest
                            log.warning("1 m lidar read failed for %s: %s", t.url, e)
                            w = None
                        if w is not None:
                            got = (check_window(sp["kind"], *w), t)
                            break
                    res_list.append((sp["id"], *(got or (None, None))))
            finally:
                for ds in handles.values():
                    ds.close()
        return res_list

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for chunk in pool.map(lambda kv: run(*kv), plan.items()):
            for sid, chk, tile in chunk:
                out[sid] = (chk, tile)
    return out
