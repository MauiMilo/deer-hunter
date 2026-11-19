"""Method-limited zones (Bear Brook's bow-only refuge east of Podunk Road)."""

import json

import pytest
from shapely.geometry import box, shape

from deerscout import zones
from deerscout.access import AccessRules
from deerscout.config import CONCORD, COOS, DATA_DIR

RULES = AccessRules.load(DATA_DIR / "access_rules.yaml", DATA_DIR / "verifications.yaml")


def cite(keys):
    return [{"id": k} for k in keys]


def write_zone(tmp_path, geom, **props):
    p = {"id": "z", "name": "Test refuge: bow only", "methods": ["archery"], "sources": ["res_7301_10"], **props}
    (tmp_path / "z.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": geom.__geo_interface__, "properties": p}]}))


def test_real_bear_brook_zone_loads_and_cites_known_sources():
    zs = zones.load(DATA_DIR / "zones", known_sources=set(RULES.sources))
    bb = next(z for z in zs if z.id == "bear-brook-archery-only")
    assert bb.methods == ["archery"]
    assert bb.approximate
    assert {"res_7301_10", "rsa_212_14"} <= set(bb.sources)
    # East of Podunk Road (about -71.36 W) in Allenstown/Deerfield, roughly 3,500 acres.
    w, s, e, n = bb.geom_wgs.bounds
    assert -71.37 < w and e < -71.31 and 43.09 < s and n < 43.15
    assert 3000 < bb.geom_ea.area / 4046.86 < 4200


def test_bear_brook_zone_is_in_concord_area_but_not_coos():
    zs = zones.load(DATA_DIR / "zones")
    assert [z.id for z in zones.in_envelope(zs, CONCORD.envelope)] == ["bear-brook-archery-only"]
    assert zones.in_envelope(zs, COOS.envelope) == []  # Coos blocks and files are unaffected


def test_block_mostly_in_zone_gets_bow_only(tmp_path):
    from pyproj import Transformer
    import shapely

    to_wgs = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)
    zone_ea = box(0, 0, 1000, 1000)
    write_zone(tmp_path, shapely.transform(zone_ea, lambda x, y: to_wgs.transform(x, y), interleaved=False))
    [z] = zones.load(tmp_path)
    inside = box(100, 100, 900, 900)
    straddle = box(900, 0, 1900, 1000)  # 10% inside
    sliver = box(980, 0, 1980, 1000)  # 2% inside
    outside = box(2000, 0, 3000, 1000)

    full = zones.limit_for(inside, [z], cite)
    assert full["methods"] == ["archery"] and full["share"] == pytest.approx(1.0, abs=0.01)
    assert full["sources"] == [{"id": "res_7301_10"}]
    part = zones.limit_for(straddle, [z], cite)
    assert part["methods"] == ["archery"] and part["share"] == pytest.approx(0.1, abs=0.01)
    assert "10% of this block" in part["note"]
    assert zones.limit_for(sliver, [z], cite) is None
    assert zones.limit_for(outside, [z], cite) is None


def test_zone_without_sources_or_methods_is_rejected(tmp_path):
    write_zone(tmp_path, box(-71.4, 43.1, -71.3, 43.2), sources=[])
    with pytest.raises(ValueError, match="source"):
        zones.load(tmp_path)
    write_zone(tmp_path, box(-71.4, 43.1, -71.3, 43.2), methods=["slingshot"])
    with pytest.raises(ValueError, match="methods"):
        zones.load(tmp_path)
    write_zone(tmp_path, box(-71.4, 43.1, -71.3, 43.2), sources=["made_up"])
    with pytest.raises(ValueError, match="unknown sources"):
        zones.load(tmp_path, known_sources=set(RULES.sources))


def test_zone_map_file_shape():
    zs = zones.in_envelope(zones.load(DATA_DIR / "zones"), CONCORD.envelope)
    fc = zones.to_geojson(zs, RULES._cite)
    f = fc["features"][0]
    assert f["properties"]["methods"] == ["archery"]
    assert f["properties"]["sources"][0]["url"].startswith("https://")
    assert shape(f["geometry"]).is_valid
