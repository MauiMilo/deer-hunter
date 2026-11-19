"""County and town boundaries from the Census Bureau's TIGERweb services (public domain)."""

from __future__ import annotations

import math

import geopandas as gpd

from .arcgis import FetchResult, layer_info, query_geojson
from .config import TIGERWEB_COUNTIES, TIGERWEB_COUSUB_SERVICE, Region
from .geo import features_to_gdf, repair
from .http import Session, SourceError

SOURCE_COUNTY = "Census TIGERweb counties"
SOURCE_TOWNS = "Census TIGERweb county subdivisions (towns)"


def county(session: Session, geoid: str) -> tuple[gpd.GeoDataFrame, FetchResult]:
    res = query_geojson(
        session,
        TIGERWEB_COUNTIES,
        source=SOURCE_COUNTY,
        where=f"GEOID='{geoid}'",
        out_fields="GEOID,NAME",
        page_size=10,
    )
    gdf = repair(features_to_gdf(res.features))
    if gdf.empty:
        raise SourceError(SOURCE_COUNTY, f"no county with GEOID {geoid}")
    return gdf, res


def find_layer_id(session: Session, service_url: str, wanted: str, *, source: str) -> int:
    info = layer_info(session, service_url, source=source)
    for lyr in info.get("layers", []):
        if lyr.get("name", "").strip().lower() == wanted.lower():
            return int(lyr["id"])
    names = [lyr.get("name") for lyr in info.get("layers", [])]
    raise SourceError(source, f"layer {wanted!r} not found; service has {names}")


def towns(session: Session, county_geoid: str) -> tuple[gpd.GeoDataFrame, FetchResult]:
    layer_id = find_layer_id(session, TIGERWEB_COUSUB_SERVICE, "County Subdivisions", source=SOURCE_TOWNS)
    state, cnty = county_geoid[:2], county_geoid[2:]
    res = query_geojson(
        session,
        f"{TIGERWEB_COUSUB_SERVICE}/{layer_id}",
        source=SOURCE_TOWNS,
        where=f"STATE='{state}' AND COUNTY='{cnty}'",
        out_fields="GEOID,NAME,BASENAME",
        page_size=200,
    )
    gdf = repair(features_to_gdf(res.features))
    if gdf.empty:
        raise SourceError(SOURCE_TOWNS, "no towns returned")
    name_col = "BASENAME" if "BASENAME" in gdf.columns else "NAME"
    gdf["town"] = gdf[name_col].astype(str).str.strip()
    return gdf[["town", "geometry"]], res


def miles_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in statute miles between two (lon, lat) points."""
    r = 3958.8
    lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def towns_within(session: Session, region: Region) -> tuple[gpd.GeoDataFrame, FetchResult]:
    """Whole towns from the region's counties whose Census internal point is within the radius.

    Returns the towns (``town``, ``miles``, ``geometry``); their union is the region's shape.
    """
    if not region.by_radius:
        raise ValueError(f"region {region.slug} has no center and radius")
    layer_id = find_layer_id(session, TIGERWEB_COUSUB_SERVICE, "County Subdivisions", source=SOURCE_TOWNS)
    states = sorted({c[:2] for c in region.counties})
    if len(states) != 1:
        raise ValueError("a region's counties must be in one state")
    county_list = ",".join(f"'{c[2:]}'" for c in region.counties)
    res = query_geojson(
        session,
        f"{TIGERWEB_COUSUB_SERVICE}/{layer_id}",
        source=SOURCE_TOWNS,
        where=f"STATE='{states[0]}' AND COUNTY IN ({county_list})",
        out_fields="GEOID,NAME,BASENAME,INTPTLAT,INTPTLON",
        page_size=200,
    )
    gdf = repair(features_to_gdf(res.features))
    if gdf.empty:
        raise SourceError(SOURCE_TOWNS, "no towns returned")
    for col in ("INTPTLAT", "INTPTLON"):
        if col not in gdf.columns:
            raise SourceError(SOURCE_TOWNS, f"towns are missing {col}, so distance from the center can't be measured")
    name_col = "BASENAME" if "BASENAME" in gdf.columns else "NAME"
    gdf["town"] = gdf[name_col].astype(str).str.strip()
    gdf["miles"] = [
        round(miles_between(region.center, (float(lon), float(lat))), 2) for lat, lon in zip(gdf["INTPTLAT"], gdf["INTPTLON"])
    ]
    inside = gdf[gdf["miles"] <= region.radius_miles].sort_values("miles")
    if inside.empty:
        raise SourceError(SOURCE_TOWNS, f"no towns within {region.radius_miles} miles of the center")
    return inside[["town", "miles", "geometry"]].reset_index(drop=True), res
