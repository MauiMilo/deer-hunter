import math

import numpy as np
import pytest
from rasterio.transform import from_origin

from deerscout import analyses, landcover, lidar1m, roads, spots

RES = 1.0
N = 241  # 240 m window at 1 m


def grid():
    c = (N - 1) / 2
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    east = (xx - c) * RES
    north = (c - yy) * RES
    return east, north


def noise(z, seed=0):
    return z + np.random.default_rng(seed).normal(0, 0.03, z.shape)


def test_bench_confirmed_on_a_real_shelf():
    east, north = grid()
    z = np.tan(math.radians(20)) * north  # steady 20 degree slope rising north
    shelf = np.abs(north) < 15
    z = np.where(shelf, 0.0, z - np.sign(north) * np.tan(math.radians(20)) * 15)
    chk = lidar1m.check_window("bench", noise(z), RES)
    assert chk.verdict == "confirmed", chk.detail


def test_bench_moves_to_a_shelf_nearby():
    east, north = grid()
    n2 = north - 22  # shelf centered 22 m north of the spot
    z = np.tan(math.radians(20)) * n2
    z = np.where(np.abs(n2) < 9, 0.0, z - np.sign(n2) * np.tan(math.radians(20)) * 9)
    chk = lidar1m.check_window("bench", noise(z), RES)
    assert chk.verdict == "moved", chk.detail
    assert chk.dy_m == pytest.approx(22, abs=6) and abs(chk.dx_m) < 6


def test_bench_not_confirmed_on_a_steady_slope():
    east, north = grid()
    z = np.tan(math.radians(22)) * north
    assert lidar1m.check_window("bench", noise(z), RES).verdict == "not_confirmed"


def test_saddle_confirmed_and_travel_axis_crosses_the_ridge():
    east, north = grid()
    z = (east**2 - north**2) / 600.0  # ridge runs east-west, ground falls north and south
    chk = lidar1m.check_window("saddle", noise(z), RES)
    assert chk.verdict == "confirmed", chk.detail
    axis = chk.travel_axis_deg
    assert min(axis, 180 - axis) < 20  # deer cross north-south


def test_saddle_not_confirmed_on_a_plane():
    east, north = grid()
    assert lidar1m.check_window("saddle", noise(0.2 * north), RES).verdict == "not_confirmed"


def test_water_surface_is_detected():
    east, north = grid()
    z = noise(np.tan(math.radians(8)) * north)
    z[north < -20] = 400.0  # a hydro-flattened pond 20 m south of the spot
    assert lidar1m.check_window("saddle", z, RES).verdict == "water"


def test_flat_but_bumpy_field_is_not_water():
    east, north = grid()
    assert lidar1m.check_window("bench", noise(np.zeros((N, N))), RES).verdict == "confirmed"


def test_parse_products_and_tile_order():
    doc = {
        "total": 2,
        "items": [
            {"downloadURL": "https://x/StagedProducts/Elevation/1m/Projects/OLD_2015/TIFF/a.tif", "publicationDate": "2020-03-30",
             "boundingBox": {"minX": -71.5, "minY": 45.0, "maxX": -71.3, "maxY": 45.2}},
            {"downloadURL": "https://x/StagedProducts/Elevation/1m/Projects/NEW_2024/TIFF/b.tif", "publicationDate": "2025-01-01",
             "boundingBox": {"minX": -71.5, "minY": 45.0, "maxX": -71.3, "maxY": 45.2}},
            {"downloadURL": "https://x/meta.xml", "boundingBox": {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1}},
        ],
    }
    tiles = lidar1m.parse_products(doc)
    assert [t.project for t in tiles] == ["OLD_2015", "NEW_2024"]
    assert [t.project for t in lidar1m.tiles_for(tiles, -71.4, 45.1)] == ["NEW_2024", "OLD_2015"]
    assert lidar1m.tiles_for(tiles, -70.0, 45.1) == []


def _spot(**kw):
    sp = {"id": "u#s1", "unit_id": "u", "kind": "bench", "point": [-71.43, 45.08], "score": 70, "confidence": "low",
          "reasons": ["x"], "travel_axis_deg": 40.0, "good_winds_from": spots.good_winds(40.0), "approach": None}
    sp.update(kw)
    return sp


class _Ctx:
    net = None


def test_apply_check_moves_spot_and_raises_confidence():
    sp = _spot()
    keep = analyses.apply_lidar_check(_Ctx(), sp, lidar1m.Check("moved", "Moved 20 m", dx_m=0.0, dy_m=20.0), None)
    assert keep and sp["lidar"]["verdict"] == "moved" and sp["lidar"]["res_m"] == 1
    assert sp["point"][1] > 45.08 and abs(sp["point"][1] - 45.08 - 20 / 111320) < 2e-5
    assert sp["confidence"] == "medium"


def test_apply_check_penalizes_and_drops():
    sp = _spot()
    assert analyses.apply_lidar_check(_Ctx(), sp, lidar1m.Check("not_confirmed", "weak"), None)
    assert sp["score"] == 70 - lidar1m.NOT_CONFIRMED_PENALTY and "weak" in sp["reasons"]
    assert not analyses.apply_lidar_check(_Ctx(), _spot(), lidar1m.Check("water", "pond"), None)
    sp2 = _spot()
    assert analyses.apply_lidar_check(_Ctx(), sp2, None, None)
    assert sp2["lidar"]["verdict"] == "not_checked" and sp2["lidar"]["res_m"] == 10


def test_saddle_check_updates_good_winds():
    sp = _spot(kind="saddle")
    analyses.apply_lidar_check(_Ctx(), sp, lidar1m.Check("confirmed", "ok", travel_axis_deg=0.0), None)
    assert sp["travel_axis_deg"] == 0.0
    assert sp["good_winds_from"] == spots.good_winds(0.0)


def test_water_distance_from_land_cover():
    data = np.full((60, 60), 41, dtype=np.uint8)
    data[:, 40:] = 11  # a lake east of column 40
    lc = landcover.LandCover(data, from_origin(0, 1800, 30, 30), "EPSG:5070", "test", 2025, "")
    # Point in column 38 (two pixels west of the lake), row 30.
    d = spots.water_distance_m(lc, 38 * 30 + 15, 1800 - 30 * 30 - 15)
    assert d == pytest.approx(60, abs=1)
    assert spots.water_distance_m(lc, 5 * 30 + 15, 1800 - 30 * 30 - 15) is None  # lake beyond the 300 m window


@pytest.mark.parametrize(
    "cls,own,gated",
    [("VI", "TOWN", True), ("vi", None, True), ("0", "PRIVATE", True), ("0", "TOWN", False), ("V", "TOWN", False), ("VII", "FEDERAL", False), (None, None, False)],
)
def test_dot_roads_you_cant_drive(cls, own, gated):
    assert roads.dot_not_drivable(cls, own) is gated
