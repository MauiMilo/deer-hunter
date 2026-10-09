"""County and town boundaries from the Census Bureau's TIGERweb services (public domain)."""

from __future__ import annotations

import geopandas as gpd

from .arcgis import FetchResult, layer_info, query_geojson
from .config import TIGERWEB_COUNTIES, TIGERWEB_COUSUB_SERVICE
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
