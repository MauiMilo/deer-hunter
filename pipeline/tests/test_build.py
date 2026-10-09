"""End-to-end run of the pipeline against fake services (no network)."""

import json
import math

import pytest
from shapely.geometry import Polygon, box

from deerscout import build as build_mod
from deerscout.config import COOS, CONSERVATION_LAYER, SQ_METERS_PER_ACRE, TIGERWEB_COUNTIES, TIGERWEB_COUSUB_SERVICE

from .conftest import ORIGIN, FakeResponse, FakeSession, feature, to_wgs, square_wgs

X0, Y0 = ORIGIN
COUNTY_SIDE = 20000.0


def side_for(acres):
    return math.sqrt(acres * SQ_METERS_PER_ACRE)


def tract(geom, tid, name, agency, pptype, access, pid=None, pname=None, oid=0):
    return feature(
        geom,
        OBJECTID=oid,
        TID=tid,
        PID=pid or tid[:-3],
        NAME=name,
        P_NAME=pname or name,
        PPTYPE=pptype,
        PPAGENCY=agency,
        PPAGENTYPE=3,
        OWNERTYPE=3,
        ACCESS=access,
        MSTATUS=3,
        ACCURACY=2,
        PROGRAM=0,
        RSIZE=-999,
    )


def make_world():
    county = square_wgs(X0, Y0, COUNTY_SIDE)
    west = to_wgs(box(X0, Y0, X0 + COUNTY_SIDE / 2, Y0 + COUNTY_SIDE))
    east = to_wgs(box(X0 + COUNTY_SIDE / 2, Y0, X0 + COUNTY_SIDE, Y0 + COUNTY_SIDE))
    s400 = side_for(400)
    s2500 = side_for(2500)
    feats = [
        tract(square_wgs(X0 + 1000, Y0 + 1000, s400), "001-001  -001", "Test State Forest", 31000, "FO", 1, oid=1),
        # two tracts of one big easement, side by side (5000 acres total -> split into blocks)
        tract(square_wgs(X0 + 3000, Y0 + 8000, s2500), "005-001  -001", "Connecticut Lakes Headwaters", 30000, "CE", 4, oid=2),
        tract(square_wgs(X0 + 3000 + s2500, Y0 + 8000, s2500), "005-001  -002", "Connecticut Lakes Headwaters", 30000, "CE", 4, oid=3),
        tract(square_wgs(X0 + 12000, Y0 + 1000, side_for(100)), "002-001  -001", "Private Preserve", 52010, "FO", 3, oid=4),
        # straddles the east county line: only the inside half should remain
        tract(square_wgs(X0 + COUNTY_SIDE - 500, Y0 + 15000, 1000), "003-001  -001", "Border Lot", 7045, "FO", 1, oid=5),
        # entirely outside the county
        tract(square_wgs(X0 + COUNTY_SIDE + 3000, Y0 + 3000, 800), "004-001  -001", "Outside Lot", 7045, "FO", 1, oid=6),
        # invalid self-intersecting ring (bowtie) inside the county
        tract(
            to_wgs(Polygon([(X0 + 15000, Y0 + 5000), (X0 + 16000, Y0 + 6000), (X0 + 16000, Y0 + 5000), (X0 + 15000, Y0 + 6000)])),
            "006-001  -001",
            "Bowtie Lot",
            7160,
            "FO",
            1,
            oid=7,
        ),
    ]
    return county, west, east, feats


def handler_for(world, fail_towns=False):
    county, west, east, feats = world

    def handler(url, params):
        if url == f"{TIGERWEB_COUNTIES}/query":
            if params.get("returnCountOnly") == "true":
                return FakeResponse({"count": 1})
            return FakeResponse({"type": "FeatureCollection", "features": [feature(county, GEOID="33007", NAME="Coos County")]})
        if url == CONSERVATION_LAYER:
            return FakeResponse({"maxRecordCount": 4})
        if url == f"{CONSERVATION_LAYER}/query":
            if params.get("returnCountOnly") == "true":
                return FakeResponse({"count": len(feats)})
            off, n = int(params["resultOffset"]), int(params["resultRecordCount"])
            return FakeResponse({"features": feats[off : off + n], "exceededTransferLimit": off + n < len(feats)})
        if url == TIGERWEB_COUSUB_SERVICE:
            if fail_towns:
                return FakeResponse({}, 503)
            return FakeResponse({"layers": [{"id": 0, "name": "Places"}, {"id": 22, "name": "County Subdivisions"}]})
        if url == f"{TIGERWEB_COUSUB_SERVICE}/22/query":
            if params.get("returnCountOnly") == "true":
                return FakeResponse({"count": 2})
            return FakeResponse(
                {
                    "features": [
                        feature(west, GEOID="1", NAME="Pittsburg town", BASENAME="Pittsburg"),
                        feature(east, GEOID="2", NAME="Colebrook town", BASENAME="Colebrook"),
                    ]
                }
            )
        raise AssertionError(f"unexpected request {url} {params}")

    return handler


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(build_mod, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr("deerscout.http.time.sleep", lambda s: None)

    def _run(**kw):
        out = tmp_path / "out"
        manifest = build_mod.build(COOS, session=FakeSession(handler_for(make_world(), **kw)), out_dir=out)
        load = lambda n: json.loads((out / n).read_text())  # noqa: E731
        return manifest, load

    return _run


def test_end_to_end_outputs(run):
    manifest, load = run()
    catalog = load("catalog.json")
    props = {p["name"]: p for p in catalog["properties"]}

    assert "Outside Lot" not in props
    assert set(props) == {"Test State Forest", "Connecticut Lakes Headwaters", "Private Preserve", "Border Lot", "Bowtie Lot"}

    sf = props["Test State Forest"]
    assert sf["acres"] == pytest.approx(400, rel=0.01)
    assert sf["access"]["status"] == "verified"
    assert sf["access"]["sources"]
    assert sf["towns"] == ["Pittsburg"]
    assert sf["wmu_units"] == ["A"]

    clhw = props["Connecticut Lakes Headwaters"]
    assert len(clhw["tract_ids"]) == 2
    assert clhw["acres"] == pytest.approx(5000, rel=0.01)
    assert clhw["access"]["status"] == "verified"
    assert len(clhw["unit_ids"]) >= 4

    assert props["Private Preserve"]["access"]["status"] == "prohibited"

    border = props["Border Lot"]
    assert border["clipped_to_region"] is True
    assert border["acres"] == pytest.approx(1000 * 500 / SQ_METERS_PER_ACRE, rel=0.02)
    assert border["towns"] == ["Colebrook"]
    assert set(border["wmu_units"]) == {"A", "B"}

    assert props["Bowtie Lot"]["acres"] > 0

    units = {u["id"]: u for u in catalog["units"]}
    for p in catalog["properties"]:
        for uid in p["unit_ids"]:
            assert units[uid]["property_id"] == p["id"]
    block_acres = sum(units[u]["acres"] for u in clhw["unit_ids"])
    assert block_acres == pytest.approx(clhw["acres"], rel=0.001)

    for u in catalog["units"]:
        s = u["score"]
        assert s["provisional"] is True
        assert 0 <= s["score"] <= 100
        assert s["coverage"] == pytest.approx(0.15)

    geo = load("properties.geojson")
    assert len(geo["features"]) == len(catalog["properties"])
    assert {f["properties"]["status"] for f in geo["features"]} == {"verified", "prohibited", "unknown"}
    blocks = load("blocks.geojson")
    assert len(blocks["features"]) == len(clhw["unit_ids"])

    m = load("manifest.json")
    assert m["counts"]["properties"] == 5
    assert all(s["status"] == "ok" for s in m["sources"])
    assert load("regulations.json")["season_year"] == "2026-27"


def test_town_failure_degrades_gracefully(run):
    manifest, load = run(fail_towns=True)
    assert any(s["status"] == "failed" for s in manifest["sources"])
    assert any("WMU" in w for w in manifest["warnings"])
    catalog = load("catalog.json")
    assert all(u["wmu"]["confidence"] == "unknown" for u in catalog["units"])
    assert len(catalog["properties"]) == 5
