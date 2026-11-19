"""Method-limited zones inside a property, e.g. Bear Brook's bow-only game refuge east of Podunk Road.

Each zone is a GeoJSON file in data/zones/ with the hunting methods allowed inside it and the
sources (ids from access_rules.yaml) for the rule. A block that overlaps a zone by at least
MIN_SHARE of its area gets the zone's limit: like a block straddling a WMU line, the stricter
rule wins for the whole block, and the app says which part of it the rule covers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely.geometry import box, mapping, shape

from .config import EQUAL_AREA, WGS84

MIN_SHARE = 0.05
METHODS = {"archery", "muzzleloader", "firearm"}


@dataclass
class Zone:
    id: str
    name: str
    methods: list[str]
    approximate: bool
    how_drawn: str
    sources: list[str]
    geom_wgs: Any
    geom_ea: Any


def load(zone_dir: Path, known_sources: set[str] | None = None) -> list[Zone]:
    zones = []
    for path in sorted(zone_dir.glob("*.geojson")) if zone_dir.exists() else []:
        for f in json.loads(path.read_text()).get("features", []):
            p = f["properties"]
            methods = list(p.get("methods") or [])
            if not methods or not set(methods) <= METHODS:
                raise ValueError(f"{path.name}: zone {p.get('id')} needs methods from {sorted(METHODS)}")
            if not p.get("sources"):
                raise ValueError(f"{path.name}: zone {p.get('id')} must cite at least one source")
            if known_sources is not None:
                unknown = set(p["sources"]) - known_sources
                if unknown:
                    raise ValueError(f"{path.name}: zone {p.get('id')} cites unknown sources {sorted(unknown)}")
            g = shape(f["geometry"])
            ea = gpd.GeoSeries([g], crs=WGS84).to_crs(EQUAL_AREA).iloc[0]
            zones.append(
                Zone(
                    id=p["id"],
                    name=p["name"],
                    methods=methods,
                    approximate=bool(p.get("approximate")),
                    how_drawn=p.get("how_drawn", ""),
                    sources=list(p["sources"]),
                    geom_wgs=g,
                    geom_ea=ea,
                )
            )
    return zones


def in_envelope(zones: list[Zone], envelope: tuple[float, float, float, float]) -> list[Zone]:
    env = box(*envelope)
    return [z for z in zones if z.geom_wgs.intersects(env)]


def limit_for(unit_geom_ea, zones: list[Zone], cite) -> dict[str, Any] | None:
    """The method limit for one block (equal-area geometry), or None. ``cite`` expands source ids."""
    area = unit_geom_ea.area
    if area <= 0:
        return None
    hits = []
    for z in zones:
        share = unit_geom_ea.intersection(z.geom_ea).area / area
        if share >= MIN_SHARE:
            hits.append((z, share))
    if not hits:
        return None
    # Several zones: only methods every one of them allows.
    allowed = set(METHODS)
    for z, _ in hits:
        allowed &= set(z.methods)
    z, share = max(hits, key=lambda h: h[1])
    return {
        "methods": sorted(allowed),
        "zone_id": z.id,
        "zone_name": z.name,
        "share": round(share, 2),
        "approximate": z.approximate,
        "note": (
            f"{round(share * 100)}% of this block is in the {z.name.split(':')[0]}, where only "
            f"{' and '.join(sorted(allowed)) or 'no method'} is allowed. The stricter rule is used for the whole block."
            if share < 0.98
            else f"This block is in the {z.name.split(':')[0]}, where only {' and '.join(sorted(allowed)) or 'no method'} is allowed."
        ),
        "how_drawn": z.how_drawn,
        "sources": cite(z.sources),
    }


def to_geojson(zones: list[Zone], cite) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(z.geom_wgs),
                "properties": {
                    "id": z.id,
                    "name": z.name,
                    "methods": z.methods,
                    "approximate": z.approximate,
                    "how_drawn": z.how_drawn,
                    "sources": cite(z.sources),
                },
            }
            for z in zones
        ],
    }
