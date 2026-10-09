"""Geometry helpers: building GeoDataFrames, repairing polygons, acreage, splitting, export."""

from __future__ import annotations

import math
from typing import Any, Iterable

import geopandas as gpd
import numpy as np
import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.geometry.base import BaseGeometry

from .config import COORD_DECIMALS, EQUAL_AREA, SQ_METERS_PER_ACRE, WGS84


def features_to_gdf(features: Iterable[dict[str, Any]], crs: str = WGS84) -> gpd.GeoDataFrame:
    rows, geoms = [], []
    for f in features:
        g = f.get("geometry")
        if not g:
            continue
        rows.append(dict(f.get("properties") or {}))
        geoms.append(shape(g))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=crs)


def polygonal(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Keep only the polygon parts of a geometry (repairs can leave stray lines/points)."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, (Polygon, MultiPolygon)):
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, (Polygon, MultiPolygon))]
    polys: list[Polygon] = []
    for p in parts:
        polys.extend(p.geoms if isinstance(p, MultiPolygon) else [p])
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else MultiPolygon(polys)


def repair(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Fix invalid polygons (self-intersections etc.) and drop anything that isn't an area."""
    out = gdf.copy()
    fixed = shapely.make_valid(out.geometry.values)
    out["geometry"] = [polygonal(g) for g in fixed]
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    return out.set_geometry("geometry")


def acres(geoms: gpd.GeoSeries) -> np.ndarray:
    """Area in acres, measured in an equal-area projection (never in degrees)."""
    if geoms.crs is None:
        raise ValueError("geometry has no coordinate system; refusing to guess units")
    return geoms.to_crs(EQUAL_AREA).area.to_numpy() / SQ_METERS_PER_ACRE


def compactness(geom: BaseGeometry) -> float:
    """Polsby-Popper score in a projected system: 1 for a circle, near 0 for a thin strip."""
    if geom.is_empty or geom.length == 0:
        return 0.0
    return float(4 * math.pi * geom.area / (geom.length**2))


def split_into_blocks(
    geom_ea: BaseGeometry, target_acres: float, min_fraction: float = 0.25
) -> list[BaseGeometry]:
    """Cut a large polygon (in the equal-area system) into roughly square blocks.

    Slivers smaller than ``min_fraction`` of a block are merged into a neighbour so the
    list doesn't fill up with useless scraps along the boundary.
    """
    side = math.sqrt(target_acres * SQ_METERS_PER_ACRE)
    minx, miny, maxx, maxy = geom_ea.bounds
    cells: list[BaseGeometry] = []
    y = miny
    while y < maxy:
        x = minx
        while x < maxx:
            part = polygonal(geom_ea.intersection(box(x, y, x + side, y + side)))
            if part is not None and part.area > 0:
                cells.append(part)
            x += side
        y += side
    if len(cells) <= 1:
        return [geom_ea]

    min_area = target_acres * SQ_METERS_PER_ACRE * min_fraction
    big = [c for c in cells if c.area >= min_area]
    small = [c for c in cells if c.area < min_area]
    if not big:
        return [shapely.union_all(cells)]
    for s in small:
        # attach each scrap to the block it shares the most boundary with (or the nearest one)
        best_i, best_shared = 0, -1.0
        for i, b in enumerate(big):
            shared = s.boundary.intersection(b.boundary).length
            if shared > best_shared:
                best_i, best_shared = i, shared
        if best_shared <= 0:
            best_i = min(range(len(big)), key=lambda i: big[i].distance(s))
        big[best_i] = polygonal(shapely.union_all([big[best_i], s])) or big[best_i]
    return big


def round_coords(geom: BaseGeometry, decimals: int = COORD_DECIMALS) -> dict[str, Any]:
    """GeoJSON dict with coordinates rounded to keep the app's data files small."""

    def rnd(coords):
        if isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (int, float)):
            return [round(float(c), decimals) for c in coords]
        return [rnd(c) for c in coords]

    gj = mapping(geom)
    return {"type": gj["type"], "coordinates": rnd(gj["coordinates"])}


def representative_lonlat(geom_wgs: BaseGeometry) -> tuple[float, float]:
    """A point guaranteed to be inside the polygon (centroids can fall outside odd shapes)."""
    p = geom_wgs.representative_point()
    return round(p.x, 5), round(p.y, 5)
