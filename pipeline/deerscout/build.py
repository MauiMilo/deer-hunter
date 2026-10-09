"""Run the whole pipeline for a region and write the files the app reads.

    python -m deerscout.build --region coos

Each source is fetched independently. If an optional source fails, the feature that needs it
is switched off and the failure is written to manifest.json; the run does not invent data.
The conservation-lands source is required: without it there is nothing to rank.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml

from . import __version__, granit, tiger, units, wmu
from .access import AccessRules
from .arcgis import FetchResult, query_geojson
from .config import (
    BLOCK_SPLIT_THRESHOLD_ACRES,
    BLOCK_TARGET_ACRES,
    CACHE_DIR,
    CONSERVATION_LAYER,
    DATA_DIR,
    EQUAL_AREA,
    OUTPUT_DIR,
    REGIONS,
    SIMPLIFY_TOLERANCE_M,
    WGS84,
    Region,
)
from .geo import features_to_gdf, polygonal, repair, representative_lonlat, round_coords
from .http import Session, SourceError, make_session
from .scoring import load_config, score_unit

log = logging.getLogger("deerscout")

SOURCE_CONSERVATION = "GRANIT Conservation/Public Lands"
MIN_PIECE_ACRES = 0.5


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(v: Any) -> Any:
    """Make values JSON-safe (NaN -> None, numpy -> python)."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item") and not isinstance(v, (list, dict, str)):
        try:
            return _clean(v.item())
        except (ValueError, AttributeError):
            return v
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def _record(manifest: dict, name: str, status: str, res: FetchResult | None = None, **extra: Any) -> None:
    entry: dict[str, Any] = {"name": name, "status": status}
    if res is not None:
        entry.update(
            {
                "url": res.url,
                "retrieved_at": res.retrieved_at,
                "features": len(res.features),
                "expected": res.expected_count,
                "pages": res.pages,
                "warnings": res.warnings,
            }
        )
    entry.update(extra)
    manifest["sources"].append(entry)


def fetch_conservation(session: Session, region: Region) -> tuple[gpd.GeoDataFrame, FetchResult]:
    res = query_geojson(session, CONSERVATION_LAYER, source=SOURCE_CONSERVATION, envelope=region.envelope)
    raw = features_to_gdf(res.features)
    if raw.empty:
        raise SourceError(SOURCE_CONSERVATION, "query returned no features")
    decoded = pd.DataFrame([granit.decode(r) for r in raw.drop(columns="geometry").to_dict("records")])
    gdf = gpd.GeoDataFrame(decoded, geometry=raw.geometry.values, crs=WGS84)
    return repair(gdf), res


def clip_to_region(tracts: gpd.GeoDataFrame, boundary: gpd.GeoDataFrame | None) -> gpd.GeoDataFrame:
    if boundary is None or boundary.empty:
        tracts = tracts.copy()
        tracts["clipped"] = False
        return tracts
    shape = boundary.to_crs(EQUAL_AREA).union_all()
    t = tracts.to_crs(EQUAL_AREA)
    inside = t.geometry.intersects(shape)
    t = t[inside].copy()
    clipped = t.geometry.intersection(shape)
    t["clipped"] = ~t.geometry.within(shape)
    t["geometry"] = [polygonal(g) for g in clipped]
    t = t[t.geometry.notna()]
    t = t[t.geometry.area / 4046.8564224 >= MIN_PIECE_ACRES]
    return t.to_crs(WGS84)


def _simplified(gdf: gpd.GeoDataFrame) -> list[dict[str, Any]]:
    ea = gdf.to_crs(EQUAL_AREA).geometry.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
    return [round_coords(g) for g in gpd.GeoSeries(ea, crs=EQUAL_AREA).to_crs(WGS84)]


def _bbox(geom) -> list[float]:
    return [round(v, 5) for v in geom.bounds]


def build(region: Region, *, session: Session | None = None, out_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    session = session or make_session()
    started = _now()
    manifest: dict[str, Any] = {
        "pipeline_version": __version__,
        "region": {"slug": region.slug, "name": region.name, "focus_towns": list(region.focus_towns)},
        "started_at": started,
        "sources": [],
        "warnings": [],
        "limitations": [],
    }

    # 1. Region boundary (optional: fall back to the search rectangle)
    county = None
    try:
        county, res = tiger.county(session, region.county_geoid)
        _record(manifest, tiger.SOURCE_COUNTY, "ok", res)
    except SourceError as e:
        _record(manifest, tiger.SOURCE_COUNTY, "failed", error=e.message)
        manifest["warnings"].append("County boundary unavailable; properties were not clipped to the county line.")

    # 2. Conservation and public lands (required)
    tracts, res = fetch_conservation(session, region)
    _record(manifest, SOURCE_CONSERVATION, "ok", res, data_published="2026-06-30")
    raw_dir = CACHE_DIR / region.slug
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "conservation_raw.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": res.features}))

    tracts = clip_to_region(tracts, county)
    log.info("tracts in region: %d", len(tracts))

    # 3. Towns (optional: needed for WMU lookup)
    towns_gdf = None
    try:
        towns_gdf, res = tiger.towns(session, region.county_geoid)
        _record(manifest, tiger.SOURCE_TOWNS, "ok", res)
    except SourceError as e:
        _record(manifest, tiger.SOURCE_TOWNS, "failed", error=e.message)
        manifest["warnings"].append("Town boundaries unavailable; town names are missing and the WMU fallback can't be used.")

    # 3b. Official WMU map (optional: falls back to town names)
    wmu_gdf = None
    try:
        res = query_geojson(session, wmu.WMU_LAYER, source=wmu.SOURCE_WMU, envelope=region.envelope)
        wmu_gdf = repair(features_to_gdf(res.features)).to_crs(EQUAL_AREA)
        if wmu_gdf.empty:
            raise SourceError(wmu.SOURCE_WMU, "no WMU polygons returned")
        _record(manifest, wmu.SOURCE_WMU, "ok", res)
    except SourceError as e:
        wmu_gdf = None
        _record(manifest, wmu.SOURCE_WMU, "failed", error=e.message)
        manifest["warnings"].append("Official WMU map unavailable; WMUs were estimated from town names.")

    # 4. Properties, overlaps, access
    props = units.build_properties(tracts)
    overlaps = units.find_overlaps(props)
    rules = AccessRules.load(DATA_DIR / "access_rules.yaml", DATA_DIR / "verifications.yaml")
    props["towns"] = units.towns_touching(props, towns_gdf)

    regs = yaml.safe_load((DATA_DIR / "regulations" / "nh-deer-2026.yaml").read_text())

    # 5. Units (blocks) and scores
    cfg = load_config(DATA_DIR / "scoring.yaml")
    unit_gdf = units.make_units(props, split_above_acres=BLOCK_SPLIT_THRESHOLD_ACRES, target_acres=BLOCK_TARGET_ACRES)
    unit_gdf["town"] = units.assign_towns(unit_gdf, towns_gdf)
    if wmu_gdf is not None:
        known = {u for season in regs["seasons"] for u in season["units"]}
        wmu_results = [w.to_dict() for w in wmu.from_layer(unit_gdf.to_crs(EQUAL_AREA).geometry.values, wmu_gdf, known_units=known)]
    else:
        wmu_results = [wmu.lookup(t).to_dict() for t in unit_gdf["town"]]
    unit_gdf["wmu"] = wmu_results

    prop_by_id = props.set_index("id")
    unit_records = []
    for _, u in unit_gdf.iterrows():
        p = prop_by_id.loc[u["property_id"]]
        signals = {
            "acres": float(u["acres"]),
            "compactness": float(u["compactness"]),
            "boundary_accuracy_code": _clean(p.get("boundary_accuracy_code")),
        }
        score = score_unit(signals, cfg).to_dict()
        lon, lat = representative_lonlat(u.geometry)
        unit_records.append(
            {
                "id": u["id"],
                "property_id": u["property_id"],
                "label": u["label"],
                "is_block": bool(u["is_block"]),
                "acres": round(float(u["acres"]), 1),
                "point": [lon, lat],
                "bbox": _bbox(u.geometry),
                "town": u["town"],
                "wmu": u["wmu"],
                "score": score,
            }
        )

    units_by_prop: dict[str, list[dict]] = {}
    for r in unit_records:
        units_by_prop.setdefault(r["property_id"], []).append(r)

    prop_records = []
    for _, p in props.iterrows():
        attrs = {k: _clean(p.get(k)) for k in granit.decode({}).keys()}
        access = rules.evaluate({**attrs, "name": p["name"], "parent_name": attrs.get("parent_name")}).to_dict()
        us = units_by_prop.get(p["id"], [])
        scored = [u["score"]["score"] for u in us if u["score"]["score"] is not None]
        lon, lat = representative_lonlat(p.geometry)
        unit_wmus = sorted({x for u in us for x in u["wmu"]["units"]})
        prop_records.append(
            _clean(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "tract_ids": p["tract_ids"],
                    "tract_names": p["tract_names"],
                    **{k: v for k, v in attrs.items() if k not in ("name", "tract_id")},
                    "acres": round(float(p["acres"]), 1),
                    "compactness": round(float(p["compactness"]), 3),
                    "clipped_to_region": bool(tracts.loc[tracts["tract_id"].isin(p["tract_ids"]), "clipped"].any()),
                    "towns": p["towns"],
                    "wmu_units": unit_wmus,
                    "access": access,
                    "overlaps": overlaps.get(p["id"], []),
                    "point": [lon, lat],
                    "bbox": _bbox(p.geometry),
                    "unit_ids": [u["id"] for u in us],
                    "best_unit_score": max(scored) if scored else None,
                }
            )
        )

    # 6. Write outputs
    out_dir.mkdir(parents=True, exist_ok=True)
    prop_geoms = _simplified(props)
    prop_index = {r["id"]: r for r in prop_records}
    prop_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": i,
                "geometry": g,
                "properties": {
                    "id": pid,
                    "name": prop_index[pid]["name"],
                    "status": prop_index[pid]["access"]["status"],
                    "acres": prop_index[pid]["acres"],
                    "score": prop_index[pid]["best_unit_score"],
                },
            }
            for i, (pid, g) in enumerate(zip(props["id"], prop_geoms))
        ],
    }
    blocks = unit_gdf[unit_gdf["is_block"]]
    unit_index = {u["id"]: u for u in unit_records}
    block_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": i,
                "geometry": g,
                "properties": {
                    "id": uid,
                    "property_id": unit_index[uid]["property_id"],
                    "label": unit_index[uid]["label"],
                    "score": unit_index[uid]["score"]["score"],
                    "status": prop_index[unit_index[uid]["property_id"]]["access"]["status"],
                },
            }
            for i, (uid, g) in enumerate(zip(blocks["id"], _simplified(blocks) if len(blocks) else []))
        ],
    }

    status_counts = pd.Series([r["access"]["status"] for r in prop_records]).value_counts().to_dict()
    manifest.update(
        {
            "finished_at": _now(),
            "counts": {
                "tracts": int(len(tracts)),
                "properties": len(prop_records),
                "units": len(unit_records),
                "blocks": int(len(blocks)),
                "access_status": {k: int(v) for k, v in status_counts.items()},
                "total_acres": round(sum(r["acres"] for r in prop_records)),
            },
        }
    )
    manifest["limitations"] += [
        "Scores currently use property size and shape only. Land cover, terrain, pressure and deer abundance are not analyzed yet, so every score is provisional.",
        "Overlapping records (for example, a state forest and an easement on the same ground) are listed separately; see each property's overlaps.",
    ]

    catalog = {
        "generated_at": manifest["finished_at"],
        "region": manifest["region"],
        "general_restrictions": rules.general_restrictions(),
        "scoring": {"weights": cfg["weights"], "provisional_below_coverage": cfg.get("provisional_below_coverage", 0.5)},
        "properties": prop_records,
        "units": unit_records,
    }

    _write(out_dir / "properties.geojson", prop_fc)
    _write(out_dir / "blocks.geojson", block_fc)
    _write(out_dir / "catalog.json", _clean(catalog))
    _write(out_dir / "regulations.json", regs)
    _write(out_dir / "manifest.json", _clean(manifest))
    return manifest


def _write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    log.info("wrote %s (%.1f KB)", path.name, path.stat().st_size / 1024)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--region", default="coos", choices=sorted(REGIONS))
    ap.add_argument("--out", type=Path, default=OUTPUT_DIR)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        manifest = build(REGIONS[args.region], out_dir=args.out)
    except SourceError as e:
        log.error("required source failed: %s", e)
        return 2
    print(json.dumps(manifest["counts"], indent=2))
    for w in manifest["warnings"]:
        log.warning(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
