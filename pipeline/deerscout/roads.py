"""Roads and trails, used to estimate how easy a block is to reach and how much human traffic it gets.

Sources:
- NH DOT road inventory (public roads, with legislative class), via GRANIT.
- OpenStreetMap (ODbL) for logging/forest roads the DOT inventory doesn't carry. Ways tagged
  access=private/no are treated as gated.
- NH Recreational Trails layer.

None of these tell us how many hunters actually use a place. They feed an *estimated* pressure
index, labeled as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import shapely
from rasterio.features import geometry_mask, rasterize
from rasterio.transform import Affine, from_origin
from scipy import ndimage
from shapely.geometry import LineString

from .arcgis import FetchResult, layer_info, query_geojson
from .config import EQUAL_AREA, WGS84
from .geo import features_to_gdf
from .http import Session, SourceError, get_json

DOT_ROADS = "https://nhgeodata.unh.edu/nhgeodata/rest/services/TN/RoadsForDOTViewer/MapServer/5"
TRAILS_SERVICE = "https://services8.arcgis.com/hg1B9Egwk1I5p300/ArcGIS/rest/services/NH_Recreational_Trails/FeatureServer"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]

SOURCE_DOT = "NH DOT roads (GRANIT)"
SOURCE_OSM = "OpenStreetMap roads (incl. logging roads)"
SOURCE_TRAILS = "NH Recreational Trails"

NEAR_ROAD_M = 400.0  # roughly a quarter mile
INTERIOR_M = 800.0  # roughly half a mile

# Residential streets and service drives are left to the DOT inventory (keeps the download small).
DRIVABLE_OSM = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "track"}
GATED_ACCESS = {"private", "no"}


def fetch_dot_roads(session: Session, envelope) -> tuple[gpd.GeoDataFrame, FetchResult]:
    res = query_geojson(
        session,
        DOT_ROADS,
        source=SOURCE_DOT,
        envelope=envelope,
        out_fields="STREET,LEGIS_CLASS,SURF_TYPE,WINTER_MAINT,OWNERSHIP_DESCR,AADT",
    )
    gdf = features_to_gdf(res.features)
    if gdf.empty:
        raise SourceError(SOURCE_DOT, "no roads returned")
    gdf["source"] = "dot"
    gdf["gated"] = False
    gdf["name"] = gdf.get("STREET")
    return gdf[["name", "source", "gated", "geometry"]], res


def overpass_query(envelope) -> str:
    w, s, e, n = envelope
    kinds = "|".join(sorted(DRIVABLE_OSM))
    return f'[out:json][timeout:240];way["highway"~"^({kinds})$"]({s},{w},{n},{e});out tags geom;'


def parse_overpass(doc: dict[str, Any]) -> gpd.GeoDataFrame:
    rows, geoms = [], []
    for el in doc.get("elements", []):
        if el.get("type") != "way" or len(el.get("geometry") or []) < 2:
            continue
        tags = el.get("tags", {})
        coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
        rows.append(
            {
                "name": tags.get("name"),
                "source": "osm",
                "highway": tags.get("highway"),
                "gated": tags.get("access") in GATED_ACCESS or tags.get("motor_vehicle") in GATED_ACCESS,
            }
        )
        geoms.append(LineString(coords))
    return gpd.GeoDataFrame(rows, geometry=geoms, crs=WGS84)


def fetch_osm_roads(session: Session, envelope) -> tuple[gpd.GeoDataFrame, str]:
    q = overpass_query(envelope)
    last = ""
    for url in OVERPASS:
        try:
            doc = get_json(session, url, {"data": q}, source=SOURCE_OSM, timeout=200, retries=2)
            gdf = parse_overpass(doc)
            if gdf.empty:
                raise SourceError(SOURCE_OSM, "no ways returned")
            return gdf, url
        except SourceError as e:
            last = e.message
    raise SourceError(SOURCE_OSM, last or "all Overpass servers failed")


def fetch_trails(session: Session, envelope) -> tuple[gpd.GeoDataFrame, list[FetchResult]]:
    info = layer_info(session, TRAILS_SERVICE, source=SOURCE_TRAILS)
    layers = [l for l in info.get("layers", []) if "line" in str(l.get("geometryType", "")).lower() or l.get("geometryType") is None]
    frames, results = [], []
    for lyr in layers:
        res = query_geojson(session, f"{TRAILS_SERVICE}/{lyr['id']}", source=SOURCE_TRAILS, envelope=envelope, out_fields="*")
        g = features_to_gdf(res.features)
        g = g[g.geometry.geom_type.isin(["LineString", "MultiLineString"])]
        if not g.empty:
            frames.append(g[["geometry"]])
        results.append(res)
    if not frames:
        raise SourceError(SOURCE_TRAILS, "no trail lines returned")
    geoms = [g for f in frames for g in f.geometry.values]
    return gpd.GeoDataFrame(geometry=geoms, crs=WGS84), results


@dataclass
class Network:
    """Road and trail lines in the equal-area system, indexed for fast distance queries."""

    drivable: list[Any]
    drivable_names: list[str | None]
    gated: list[Any]
    trails: list[Any]

    def __post_init__(self) -> None:
        self._dtree = shapely.STRtree(self.drivable) if self.drivable else None
        self._gtree = shapely.STRtree(self.gated) if self.gated else None
        self._ttree = shapely.STRtree(self.trails) if self.trails else None
        self._grid: tuple[np.ndarray, Affine] | None = None

    def build_distance_grid(self, bounds, res: float = 30.0) -> None:
        """Distance (m) from every cell to the nearest drivable road, on a grid over `bounds`.

        Drawing the roads once and measuring distance per cell is fast and light on memory,
        unlike buffering thousands of road lines as shapes.
        """
        if not self.drivable:
            return
        minx, miny, maxx, maxy = bounds
        pad = INTERIOR_M * 2
        minx, miny, maxx, maxy = minx - pad, miny - pad, maxx + pad, maxy + pad
        w = int(np.ceil((maxx - minx) / res))
        h = int(np.ceil((maxy - miny) / res))
        tr = from_origin(minx, maxy, res, res)
        lines = [g for g in self.drivable if g.intersects(shapely.box(minx, miny, maxx, maxy))]
        if not lines:
            dist = np.full((h, w), np.inf, dtype=np.float32)
        else:
            on_road = rasterize(((g, 1) for g in lines), out_shape=(h, w), transform=tr, fill=0, all_touched=True, dtype="uint8")
            dist = (ndimage.distance_transform_edt(on_road == 0) * res).astype(np.float32)
        self._grid = (dist, tr)

    def _grid_shares(self, geom_ea) -> tuple[float, float] | None:
        if self._grid is None:
            return None
        dist, tr = self._grid
        inv = ~tr
        minx, miny, maxx, maxy = geom_ea.bounds
        c0, r0 = inv @ (minx, maxy)
        c1, r1 = inv @ (maxx, miny)
        r0, c0 = max(0, int(r0)), max(0, int(c0))
        r1, c1 = min(dist.shape[0], int(np.ceil(r1))), min(dist.shape[1], int(np.ceil(c1)))
        if r1 <= r0 or c1 <= c0:
            return None
        sub = dist[r0:r1, c0:c1]
        inside = geometry_mask([geom_ea], out_shape=sub.shape, transform=tr @ Affine.translation(c0, r0), invert=True, all_touched=True)
        vals = sub[inside]
        if vals.size == 0:
            return None
        return float((vals <= NEAR_ROAD_M).mean()), float((vals > INTERIOR_M).mean())

    @classmethod
    def build(cls, roads: gpd.GeoDataFrame | None, trails: gpd.GeoDataFrame | None) -> "Network":
        drivable, names, gated, trail = [], [], [], []
        if roads is not None and not roads.empty:
            r = roads.to_crs(EQUAL_AREA).explode(index_parts=False)
            for geom, is_gated, name in zip(r.geometry.values, r["gated"].values, r["name"].values):
                if geom is None or geom.is_empty:
                    continue
                if is_gated:
                    gated.append(geom)
                else:
                    drivable.append(geom)
                    names.append(name if isinstance(name, str) and name.strip() else None)
        if trails is not None and not trails.empty:
            trail = [g for g in trails.to_crs(EQUAL_AREA).explode(index_parts=False).geometry.values if g is not None and not g.is_empty]
        return cls(drivable, names, gated, trail)


def _nearest(tree, geoms, g) -> tuple[float, int] | None:
    if tree is None:
        return None
    i = int(tree.nearest(g))
    return float(g.distance(geoms[i])), i


def unit_signals(net: Network, geom_ea) -> dict[str, Any]:
    """Distances and shares for one unit polygon (equal-area meters)."""
    out: dict[str, Any] = {}
    area = geom_ea.area
    if area <= 0:
        return out
    hit = _nearest(net._dtree, net.drivable, geom_ea)
    if hit is not None:
        dist, i = hit
        out["road_min_dist_m"] = round(dist, 1)
        name = net.drivable_names[i]
        if not name:
            # Nearest road is unnamed: look for the nearest named one within 3 km for directions.
            cand = net._dtree.query(geom_ea.buffer(3000))
            named = [(geom_ea.distance(net.drivable[j]), net.drivable_names[j]) for j in cand if net.drivable_names[j]]
            name = min(named)[1] if named else None
        out["nearest_road_name"] = name
        rp = geom_ea.representative_point()
        out["center_to_road_m"] = round(_nearest(net._dtree, net.drivable, rp)[0], 1)
        shares = net._grid_shares(geom_ea)
        if shares is not None:
            near, far = shares
        else:
            local = [net.drivable[j] for j in net._dtree.query(geom_ea.buffer(INTERIOR_M))]
            if local:
                lines = shapely.union_all(local)
                near = geom_ea.intersection(lines.buffer(NEAR_ROAD_M, quad_segs=4)).area / area
                far = geom_ea.difference(lines.buffer(INTERIOR_M, quad_segs=4)).area / area
            else:
                near, far = 0.0, 1.0
        out["share_near_road"] = round(float(near), 4)
        out["share_interior"] = round(float(far), 4)
    ghit = _nearest(net._gtree, net.gated, geom_ea)
    if ghit is not None:
        out["gated_road_min_dist_m"] = round(ghit[0], 1)
    if net._ttree is not None:
        zone = geom_ea.buffer(200)
        km = sum(zone.intersection(net.trails[j]).length for j in net._ttree.query(zone)) / 1000
        out["trail_km_per_km2"] = round(float(km / (zone.area / 1e6)), 3)
    return out
