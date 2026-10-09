import math

import geopandas as gpd
import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry import GeometryCollection

from deerscout.config import EQUAL_AREA, SQ_METERS_PER_ACRE, WGS84
from deerscout.geo import acres, compactness, polygonal, repair, round_coords, split_into_blocks

from .conftest import ORIGIN, square_wgs


def test_acres_of_one_square_kilometer():
    sq = square_wgs(*ORIGIN, 1000)
    a = acres(gpd.GeoSeries([sq], crs=WGS84))[0]
    assert a == pytest.approx(247.105, rel=0.002)  # 1 km^2 = 247.105 acres


def test_acres_of_a_section_square_mile():
    side = 1609.344
    a = acres(gpd.GeoSeries([square_wgs(*ORIGIN, side)], crs=WGS84))[0]
    assert a == pytest.approx(640.0, rel=0.002)


def test_acres_refuses_unknown_crs():
    with pytest.raises(ValueError):
        acres(gpd.GeoSeries([box(0, 0, 1, 1)]))


def test_acres_never_computed_in_degrees():
    # Same square measured naively in degrees would be ~0.0001 "acres"; real answer ~247.
    sq = square_wgs(*ORIGIN, 1000)
    assert sq.area < 1e-3
    assert acres(gpd.GeoSeries([sq], crs=WGS84))[0] > 200


def test_crs_round_trip_is_lossless():
    fwd = Transformer.from_crs(WGS84, EQUAL_AREA, always_xy=True)
    back = Transformer.from_crs(EQUAL_AREA, WGS84, always_xy=True)
    lon, lat = -71.4, 45.05
    x, y = fwd.transform(lon, lat)
    lon2, lat2 = back.transform(x, y)
    assert lon2 == pytest.approx(lon, abs=1e-9)
    assert lat2 == pytest.approx(lat, abs=1e-9)


def test_crs_axis_order_is_lon_lat():
    # Pittsburg, NH must land inside the conterminous-US Albers extent, east of center.
    x, y = Transformer.from_crs(WGS84, EQUAL_AREA, always_xy=True).transform(-71.4, 45.05)
    assert 1.8e6 < x < 2.2e6
    assert 2.5e6 < y < 2.9e6


def test_repair_fixes_bowtie_polygon():
    bowtie = Polygon([(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)])
    assert not bowtie.is_valid
    out = repair(gpd.GeoDataFrame({"a": [1]}, geometry=[bowtie], crs=EQUAL_AREA))
    assert len(out) == 1
    assert out.geometry.iloc[0].is_valid
    assert out.geometry.iloc[0].area == pytest.approx(2.0)


def test_repair_drops_non_area_geometry():
    gdf = gpd.GeoDataFrame({"a": [1, 2]}, geometry=[LineString([(0, 0), (1, 1)]), box(0, 0, 1, 1)], crs=EQUAL_AREA)
    out = repair(gdf)
    assert out["a"].tolist() == [2]


def test_polygonal_extracts_polygons_from_collection():
    gc = GeometryCollection([box(0, 0, 1, 1), LineString([(0, 0), (3, 3)]), Point(5, 5)])
    assert polygonal(gc).area == pytest.approx(1.0)
    assert polygonal(GeometryCollection([Point(0, 0)])) is None


def test_compactness_circle_vs_strip():
    circle = Point(0, 0).buffer(1000, quad_segs=64)
    strip = box(0, 0, 10000, 50)
    assert compactness(circle) == pytest.approx(1.0, rel=0.01)
    assert compactness(strip) < 0.05


def test_split_into_blocks_preserves_area():
    target = 1000.0
    side = math.sqrt(target * SQ_METERS_PER_ACRE)
    big = box(0, 0, side * 3.5, side * 2.2)
    blocks = split_into_blocks(big, target)
    assert sum(b.area for b in blocks) == pytest.approx(big.area, rel=1e-9)
    assert 4 <= len(blocks) <= 8
    for b in blocks:
        assert b.area >= 0.25 * target * SQ_METERS_PER_ACRE


def test_split_small_polygon_returns_itself():
    small = box(0, 0, 100, 100)
    assert split_into_blocks(small, 1000.0) == [small]


def test_round_coords_limits_precision():
    gj = round_coords(box(-71.123456789, 45.987654321, -71.0, 46.0), decimals=5)
    xs = [c for ring in gj["coordinates"] for pt in ring for c in pt]
    assert all(round(c, 5) == c for c in xs)
