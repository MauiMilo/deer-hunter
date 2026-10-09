"""Turn GRANIT tracts into properties, and large properties into rankable blocks."""

from __future__ import annotations

import re
import string
from typing import Any

import geopandas as gpd
import pandas as pd
import shapely

from .config import EQUAL_AREA, SQ_METERS_PER_ACRE, WGS84
from .geo import compactness, polygonal, split_into_blocks

GROUP_KEYS = ("group_id", "agency_code", "protection_type_code", "public_access_code")


def _slug(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def group_id(row: pd.Series) -> str:
    """Tracts that belong to the same parent project share an id (GRANIT 'PID')."""
    pid = row.get("parent_id")
    if isinstance(pid, str) and pid.strip("- "):
        return pid
    return str(row.get("tract_id") or row.name)


def build_properties(tracts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Merge tracts into properties.

    Tracts merge only if they share a parent AND the attributes that drive legal access
    (agency, protection type, public-access code), so one property never mixes rules.
    """
    t = tracts.copy()
    t["group_id"] = t.apply(group_id, axis=1)
    for k in GROUP_KEYS:
        t[k] = t[k].astype(object).where(t[k].notna(), None)

    rows = []
    for key, g in t.groupby(list(GROUP_KEYS), dropna=False, sort=True):
        g_ea = g.to_crs(EQUAL_AREA)
        geom = polygonal(shapely.union_all(g_ea.geometry.values))
        if geom is None:
            continue
        biggest = g_ea.geometry.area.idxmax()
        lead = g.loc[biggest]
        rows.append(
            {
                **{c: lead.get(c) for c in tracts.columns if c not in ("geometry",)},
                "group_id": key[0],
                "name": lead.get("parent_name") or lead.get("name"),
                "tract_ids": sorted(str(x) for x in g["tract_id"].dropna()),
                "tract_names": sorted({str(x) for x in g["name"].dropna()}),
                "acres": geom.area / SQ_METERS_PER_ACRE,
                "compactness": compactness(geom),
                "geometry": geom,
            }
        )
    props = gpd.GeoDataFrame(rows, geometry="geometry", crs=EQUAL_AREA)
    props["name"] = props["name"].fillna("Unnamed conservation land")

    base = props["group_id"].map(lambda s: "p-" + _slug(str(s)))
    dup = base.duplicated(keep=False)
    props["id"] = base
    if dup.any():
        props.loc[dup, "id"] = [
            f"{b}-{_slug(str(a))}-{_slug(str(p))}"
            for b, a, p in zip(base[dup], props.loc[dup, "agency_code"], props.loc[dup, "protection_type_code"])
        ]
    props["id"] = _dedupe(props["id"].tolist())
    return props.to_crs(WGS84)


def _dedupe(ids: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i in ids:
        n = seen.get(i, 0)
        out.append(i if n == 0 else f"{i}-{n + 1}")
        seen[i] = n + 1
    return out


def find_overlaps(props: gpd.GeoDataFrame, min_share: float = 0.2) -> dict[str, list[dict[str, Any]]]:
    """Report properties whose areas overlap (e.g., a fee tract and an easement on the same land)."""
    ea = props.to_crs(EQUAL_AREA)
    sindex = ea.sindex
    out: dict[str, list[dict[str, Any]]] = {pid: [] for pid in ea["id"]}
    geoms = ea.geometry.values
    ids = ea["id"].tolist()
    names = ea["name"].tolist()
    for i, gi in enumerate(geoms):
        for j in sindex.query(gi, predicate="intersects"):
            if j <= i:
                continue
            inter = gi.intersection(geoms[j]).area
            if inter <= 0:
                continue
            share = inter / min(gi.area, geoms[j].area)
            if share >= min_share:
                acres = round(inter / SQ_METERS_PER_ACRE)
                out[ids[i]].append({"id": ids[j], "name": names[j], "shared_acres": acres})
                out[ids[j]].append({"id": ids[i], "name": names[i], "shared_acres": acres})
    return out


def grid_label(col: int, row: int) -> str:
    letters = string.ascii_uppercase
    col_label = letters[col] if col < 26 else letters[col // 26 - 1] + letters[col % 26]
    return f"{col_label}{row + 1}"


def make_units(
    props: gpd.GeoDataFrame, *, split_above_acres: float, target_acres: float
) -> gpd.GeoDataFrame:
    """One unit per small property; large properties become a grid of labeled blocks.

    Block labels read like a map grid: letters run west to east, numbers north to south.
    """
    ea = props.to_crs(EQUAL_AREA)
    rows = []
    for _, p in ea.iterrows():
        if p["acres"] <= split_above_acres:
            rows.append(
                {
                    "id": p["id"],
                    "property_id": p["id"],
                    "label": None,
                    "is_block": False,
                    "geometry": p.geometry,
                }
            )
            continue
        blocks = split_into_blocks(p.geometry, target_acres)
        minx, _, _, maxy = p.geometry.bounds
        side = (target_acres * SQ_METERS_PER_ACRE) ** 0.5
        cells = []
        for b in blocks:
            c = b.representative_point()
            cells.append((int((maxy - c.y) // side), int((c.x - minx) // side)))  # (row, col)
        labels = _dedupe([grid_label(col, row) for row, col in cells])
        order = sorted(range(len(blocks)), key=lambda k: (cells[k], labels[k]))
        for k in order:
            rows.append(
                {
                    "id": f"{p['id']}~{labels[k]}",
                    "property_id": p["id"],
                    "label": f"Block {labels[k]}",
                    "is_block": True,
                    "geometry": blocks[k],
                }
            )
    units = gpd.GeoDataFrame(rows, geometry="geometry", crs=EQUAL_AREA)
    units["acres"] = units.geometry.area / SQ_METERS_PER_ACRE
    units["compactness"] = [compactness(g) for g in units.geometry]
    return units.to_crs(WGS84)


def assign_towns(units: gpd.GeoDataFrame, towns: gpd.GeoDataFrame | None) -> pd.Series:
    """Town containing each unit's interior point (None when towns aren't available)."""
    if towns is None or towns.empty:
        return pd.Series([None] * len(units), index=units.index)
    pts = gpd.GeoDataFrame(geometry=units.geometry.representative_point(), crs=units.crs).to_crs(towns.crs)
    joined = gpd.sjoin(pts, towns[["town", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined["town"].reindex(units.index).astype(object).where(lambda s: s.notna(), None)


def towns_touching(props: gpd.GeoDataFrame, towns: gpd.GeoDataFrame | None) -> list[list[str]]:
    if towns is None or towns.empty:
        return [[] for _ in range(len(props))]
    j = gpd.sjoin(props[["id", "geometry"]], towns[["town", "geometry"]].to_crs(props.crs), how="left", predicate="intersects")
    by = j.groupby("id")["town"].apply(lambda s: sorted({t for t in s if isinstance(t, str)}))
    return [by.get(i, []) for i in props["id"]]
