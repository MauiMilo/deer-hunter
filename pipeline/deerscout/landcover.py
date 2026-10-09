"""Land cover from the USGS National Land Cover Database (NLCD), 30 m pixels, public domain.

Annual NLCD (newest year available) is tried first through the MRLC web coverage service;
the 2021 NLCD release is the fallback. Each pixel is one class; we only report what NLCD
classes actually mean (see CLASSES). NLCD cannot identify tree species or understory density.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.merge import merge
from rasterio.transform import Affine
from rasterio.windows import from_bounds

from .http import Session, SourceError, get_bytes

SOURCE = "USGS NLCD land cover"

# NLCD class codes and official short names. Class 52 (Shrub/Scrub) explicitly includes
# "young trees in an early successional stage", which in this mostly-forested region is
# usually regrowth after logging.
CLASSES = {
    11: "Open water",
    12: "Perennial ice/snow",
    21: "Developed, open space",
    22: "Developed, low intensity",
    23: "Developed, medium intensity",
    24: "Developed, high intensity",
    31: "Barren land",
    41: "Deciduous forest",
    42: "Evergreen forest",
    43: "Mixed forest",
    52: "Shrub/scrub (incl. young regrowth)",
    71: "Grassland/herbaceous",
    81: "Pasture/hay",
    82: "Cultivated crops",
    90: "Woody wetlands",
    95: "Emergent herbaceous wetlands",
}

GROUPS = {
    "deciduous": [41],
    "evergreen": [42],
    "mixed": [43],
    "young": [52],
    "herbaceous": [71],
    "agriculture": [81, 82],
    "woody_wetland": [90],
    "open_wetland": [95],
    "water": [11, 12],
    "developed": [21, 22, 23, 24],
    "barren": [31],
}
FOREST = [41, 42, 43, 90]
OPENING = [52, 71, 81, 82, 95]

# The legend colors NLCD publishes, used for the app's land cover layer.
COLORS = {
    11: (70, 107, 159), 12: (209, 222, 248), 21: (222, 197, 197), 22: (217, 146, 130), 23: (235, 0, 0),
    24: (171, 0, 0), 31: (179, 172, 159), 41: (104, 171, 95), 42: (28, 95, 44), 43: (181, 197, 143),
    52: (204, 184, 121), 71: (223, 223, 194), 81: (220, 217, 57), 82: (171, 108, 40), 90: (184, 217, 235),
    95: (108, 159, 184),
}

PIXEL_M = 30.0

DMS_WCS = "https://dmsdata.cr.usgs.gov/geoserver/mrlc_Land-Cover-Native_conus_year_data/wcs"
LEGACY_WCS = "https://www.mrlc.gov/geoserver/mrlc_download/NLCD_2021_Land_Cover_L48/wcs"
LEGACY_ID = "mrlc_download__NLCD_2021_Land_Cover_L48"


@dataclass
class LandCover:
    data: np.ndarray  # uint8 class codes
    transform: Affine
    crs: str
    product: str
    year: int | None
    url: str

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        h, w = self.data.shape
        minx, maxy = self.transform @ (0, 0)
        maxx, miny = self.transform @ (w, h)
        return minx, miny, maxx, maxy


def pick_annual_coverage(coverage_ids: list[str]) -> tuple[str, int] | None:
    """Newest-year land cover coverage from a capabilities list (skips change/confidence products)."""
    best: tuple[str, int] | None = None
    for cid in coverage_ids:
        low = cid.lower()
        if not ("lndcov" in low or "land_cover" in low or "landcover" in low):
            continue
        if any(x in low for x in ("chg", "change", "conf", "smy", "imp", "spcdoy")):
            continue
        years = [int(y) for y in re.findall(r"(?<!\d)(19[89]\d|20[0-4]\d)(?!\d)", cid)]
        if not years:
            continue
        y = max(years)
        if best is None or y > best[1]:
            best = (cid, y)
    return best


def coverage_ids(capabilities_xml: str) -> list[str]:
    return re.findall(r"<(?:wcs:)?CoverageId>\s*([^<\s]+)\s*</(?:wcs:)?CoverageId>", capabilities_xml)


def _tiles(bounds: tuple[float, float, float, float], max_px: int = 1500) -> list[tuple[float, float, float, float]]:
    """Split a bounding box (snapped to the 30 m grid) into request-sized pieces."""
    minx, miny, maxx, maxy = bounds
    minx = np.floor(minx / PIXEL_M) * PIXEL_M
    miny = np.floor(miny / PIXEL_M) * PIXEL_M
    maxx = np.ceil(maxx / PIXEL_M) * PIXEL_M
    maxy = np.ceil(maxy / PIXEL_M) * PIXEL_M
    step = max_px * PIXEL_M
    out = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            out.append((x, y, min(x + step, maxx), min(y + step, maxy)))
            x += step
        y += step
    return out


def _get_coverage(session: Session, base: str, cid: str, b: tuple[float, float, float, float]) -> rasterio.io.MemoryFile:
    params = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": cid,
        "format": "image/tiff",
        "subset": [f"X({b[0]},{b[2]})", f"Y({b[1]},{b[3]})"],
    }
    # A 1500 x 1500 tile of 8-bit classes is ~2 MB; anything far bigger means the area limit was ignored.
    body, ctype = get_bytes(session, base, params, source=SOURCE, max_bytes=40_000_000)
    if body[:4] not in (b"II*\x00", b"MM\x00*"):
        snippet = body[:300].decode("utf-8", "replace")
        raise SourceError(SOURCE, f"coverage {cid} returned {ctype or 'non-TIFF'}: {snippet}")
    return rasterio.io.MemoryFile(io.BytesIO(body))


def _download(session: Session, base: str, cid: str, bounds) -> tuple[np.ndarray, Affine, str]:
    files = [_get_coverage(session, base, cid, b) for b in _tiles(bounds)]
    datasets = [f.open() for f in files]
    try:
        crs = datasets[0].crs.to_string() if datasets[0].crs else "EPSG:5070"
        if len(datasets) == 1:
            arr = datasets[0].read(1)
            transform = datasets[0].transform
        else:
            mosaic, transform = merge(datasets)
            arr = mosaic[0]
    finally:
        for d in datasets:
            d.close()
        for f in files:
            f.close()
    return arr.astype(np.uint8), transform, crs


def validate(arr: np.ndarray) -> float:
    """Share of pixels holding a real NLCD class (the rest are no-data / out of range)."""
    if arr.size == 0:
        return 0.0
    valid = np.isin(arr, list(CLASSES))
    return float(valid.mean())


def fetch(session: Session, bounds_5070: tuple[float, float, float, float]) -> tuple[LandCover, list[str]]:
    """Newest land cover available for the area. Returns (land cover, notes on what was tried)."""
    tried: list[str] = []
    try:
        caps, _ = get_bytes(
            session, DMS_WCS, {"service": "WCS", "version": "2.0.1", "request": "GetCapabilities"}, source=SOURCE, max_bytes=30_000_000
        )
        pick = pick_annual_coverage(coverage_ids(caps.decode("utf-8", "replace")))
        if pick:
            cid, year = pick
            arr, tr, crs = _download(session, DMS_WCS, cid, bounds_5070)
            share = validate(arr)
            if share >= 0.5:
                return LandCover(arr, tr, crs, f"Annual NLCD ({cid})", year, DMS_WCS), tried
            tried.append(f"Annual NLCD {cid}: only {share:.0%} valid pixels")
        else:
            tried.append("Annual NLCD: no land cover coverage listed in capabilities")
    except SourceError as e:
        tried.append(f"Annual NLCD: {e.message}")

    arr, tr, crs = _download(session, LEGACY_WCS, LEGACY_ID, bounds_5070)
    share = validate(arr)
    if share < 0.5:
        raise SourceError(SOURCE, f"NLCD 2021 returned only {share:.0%} valid pixels")
    return LandCover(arr, tr, crs, "NLCD 2021 (CONUS)", 2021, LEGACY_WCS), tried


# ------------------------------------------------------------------- per-unit statistics


def unit_stats(lc: LandCover, geom_5070) -> dict[str, Any] | None:
    """Land cover make-up and edge density inside one polygon (polygon in the raster's CRS)."""
    minx, miny, maxx, maxy = geom_5070.bounds
    r_minx, r_miny, r_maxx, r_maxy = lc.bounds
    if maxx <= r_minx or minx >= r_maxx or maxy <= r_miny or miny >= r_maxy:
        return None
    win = from_bounds(max(minx, r_minx), max(miny, r_miny), min(maxx, r_maxx), min(maxy, r_maxy), lc.transform)
    win = win.round_offsets().round_lengths()
    r0, c0 = int(win.row_off), int(win.col_off)
    h, w = int(win.height), int(win.width)
    if h <= 0 or w <= 0:
        return None
    sub = lc.data[r0 : r0 + h, c0 : c0 + w]
    sub_tr = lc.transform @ Affine.translation(c0, r0)
    inside = geometry_mask([geom_5070], out_shape=sub.shape, transform=sub_tr, invert=True, all_touched=False)
    vals = sub[inside]
    vals = vals[np.isin(vals, list(CLASSES))]
    if vals.size < 5:
        return None
    land = vals[~np.isin(vals, GROUPS["water"])]
    n_land = max(1, land.size)
    shares = {g: float(np.isin(land, codes).sum()) / n_land for g, codes in GROUPS.items() if g != "water"}
    shares["water"] = float(np.isin(vals, GROUPS["water"]).sum()) / vals.size
    forest = shares["deciduous"] + shares["evergreen"] + shares["mixed"] + shares["woody_wetland"]
    conifer_share_of_forest = (shares["evergreen"] + 0.5 * shares["mixed"]) / forest if forest > 0 else 0.0

    # Forest/opening edge: count neighbouring pixel pairs (both inside) of forest next to opening.
    is_forest = np.isin(sub, FOREST) & inside
    is_open = np.isin(sub, OPENING) & inside
    pairs = (
        (is_forest[:, :-1] & is_open[:, 1:]).sum()
        + (is_open[:, :-1] & is_forest[:, 1:]).sum()
        + (is_forest[:-1, :] & is_open[1:, :]).sum()
        + (is_open[:-1, :] & is_forest[1:, :]).sum()
    )
    hectares = n_land * PIXEL_M * PIXEL_M / 10000
    edge_m_per_ha = float(pairs) * PIXEL_M / hectares if hectares > 0 else 0.0
    return {
        "lc_pixels": int(vals.size),
        "lc_shares": {k: round(v, 4) for k, v in shares.items()},
        "forest": round(forest, 4),
        "conifer_share_of_forest": round(conifer_share_of_forest, 4),
        "food_openings": round(shares["young"] + shares["herbaceous"] + shares["agriculture"], 4),
        "edge_m_per_ha": round(edge_m_per_ha, 1),
    }


def to_rgba(lc: LandCover) -> np.ndarray:
    """Color image of the land cover (transparent where no data) for the map layer."""
    h, w = lc.data.shape
    img = np.zeros((h, w, 4), dtype=np.uint8)
    for code, (r, g, b) in COLORS.items():
        m = lc.data == code
        img[m] = (r, g, b, 200)
    return img
