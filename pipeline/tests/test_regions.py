"""The list of regions the app can show, and the towns-within-a-radius rule."""

import json

import pytest

from deerscout import regions, tiger
from deerscout.config import CONCORD, COOS, OUTPUT_DIR, REGIONS


def test_regions_json_matches_config():
    """web/public/data/regions.json is written from config.py; rerun `python -m deerscout.regions` if this fails."""
    assert (OUTPUT_DIR / "regions.json").read_text() == regions.render()


def test_every_region_has_its_own_folder_path():
    idx = regions.index()
    assert idx["default"] in REGIONS
    paths = [r["path"] for r in idx["regions"]]
    assert len(set(paths)) == len(paths)
    assert all(p == f"/data/{r['slug']}/" for p, r in zip(paths, idx["regions"]))


def test_coos_keeps_its_map_view_and_starting_point():
    coos = next(r for r in regions.index()["regions"] if r["slug"] == "coos")
    assert coos["center"] == [-71.3, 45.05]
    assert coos["home"] == {"label": "Pittsburg village", "lon": -71.3912, "lat": 45.0515}


def test_one_county_region_still_reports_its_county():
    assert COOS.county_geoid == "33007"
    with pytest.raises(ValueError):
        CONCORD.county_geoid  # noqa: B018 - a radius region has no single county


def test_miles_between():
    # Concord State House to Manchester City Hall is about 16 miles in a straight line.
    assert tiger.miles_between((-71.5381, 43.2067), (-71.4634, 42.9912)) == pytest.approx(15.3, abs=0.5)
    assert tiger.miles_between((-71.5, 43.2), (-71.5, 43.2)) == 0


def test_towns_within_keeps_only_towns_inside_the_radius():
    from shapely.geometry import box

    from deerscout.config import TIGERWEB_COUSUB_SERVICE

    from .conftest import FakeResponse, FakeSession, feature

    def town(name, lon, lat):
        return feature(box(lon - 0.05, lat - 0.05, lon + 0.05, lat + 0.05), BASENAME=name, NAME=name, GEOID=name, INTPTLAT=f"+{lat}", INTPTLON=f"{lon}")

    feats = [
        town("Concord", -71.54, 43.21),
        town("Weare", -71.73, 43.09),  # ~13 mi
        town("Laconia", -71.47, 43.53),  # ~22 mi
        town("Keene", -72.28, 42.93),  # ~42 mi
    ]
    seen = {}

    def handler(url, params):
        if url == TIGERWEB_COUSUB_SERVICE:
            return FakeResponse({"layers": [{"id": 22, "name": "County Subdivisions"}]})
        if params.get("returnCountOnly") == "true":
            return FakeResponse({"count": len(feats)})
        seen["where"] = params.get("where")
        return FakeResponse({"features": feats})

    gdf, _ = tiger.towns_within(FakeSession(handler), CONCORD)
    assert list(gdf["town"]) == ["Concord", "Weare", "Laconia"]  # nearest first; Keene is too far
    assert "COUNTY IN ('001','011','013','015','017','019')" in seen["where"]
    assert json.loads(gdf.to_json())["features"][0]["properties"]["miles"] < 1


def test_each_region_keeps_only_its_own_parking():
    from deerscout import build

    comstock = {"name": "Old log yard, Comstock Hill", "lon": -71.33, "lat": 45.12}  # Pittsburg
    bow = {"name": "Somewhere in Bow", "lon": -71.53, "lat": 43.13}
    assert build.parking_in(COOS, [comstock, bow]) == [comstock]
    assert build.parking_in(CONCORD, [comstock, bow]) == [bow]


def test_real_parking_file_still_gives_coos_its_log_yard():
    from deerscout import build

    names = [p["name"] for p in build.parking_in(COOS, build.load_parking())]
    assert "Old log yard, Comstock Hill" in names
    assert build.parking_in(CONCORD, build.load_parking()) == []
