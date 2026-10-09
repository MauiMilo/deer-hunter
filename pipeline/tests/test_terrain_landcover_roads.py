"""Phase 2 analysis on synthetic rasters and lines with known answers."""

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, box

from deerscout import landcover, roads, terrain
from deerscout.landcover import LandCover

RES = 5.0


def dem_from(fn, half=600.0, res=RES):
    xs = np.arange(-half + res / 2, half, res)
    ys = np.arange(half - res / 2, -half, -res)  # north to south rows
    X, Y = np.meshgrid(xs, ys)
    z = fn(X, Y).astype(np.float32)
    return terrain.Dem(z, from_origin(-half, half, res, res), res)


def ridge_with_saddle(X, Y):
    # East-west ridge with a dip (saddle) in the middle, valleys to the north and south.
    ridge = 60 * np.exp(-((Y / 160) ** 2))
    dip = 25 * np.exp(-((X / 90) ** 2)) * np.exp(-((Y / 160) ** 2))
    return 400 + ridge - dip


def hillside_with_bench(X, Y):
    # Ground rises to the north at ~27 degrees, with a 40 m wide flat shelf.
    y = Y.copy()
    rise = np.where(y < 0, 0.5 * y, np.where(y < 40, 0.0, 0.5 * (y - 40)))
    return 300 + rise


def test_slope_and_aspect_of_a_plane():
    dem = dem_from(lambda X, Y: 100 + 0.1 * X)  # rises to the east -> faces west
    t = terrain.derive(dem)
    mid = t.slope_deg[100:140, 100:140]
    assert np.nanmean(mid) == pytest.approx(np.degrees(np.arctan(0.1)), abs=0.2)
    assert np.nanmedian(t.aspect_deg[100:140, 100:140]) == pytest.approx(270, abs=1)


def test_aspect_of_north_facing_slope():
    dem = dem_from(lambda X, Y: 100 - 0.2 * Y)  # drops to the north
    t = terrain.derive(dem)
    a = np.nanmedian(t.aspect_deg[100:140, 100:140])
    assert min(a, 360 - a) < 1


def test_finds_saddle_with_correct_travel_axis():
    dem = dem_from(ridge_with_saddle)
    t = terrain.derive(dem)
    feats = [f for f in terrain.find_features(dem, t) if f.kind == "saddle"]
    assert feats, "expected a saddle"
    best = min(feats, key=lambda f: abs(f.x) + abs(f.y))
    assert abs(best.x) < 60 and abs(best.y) < 60
    # Ridge runs east-west, so travel through the saddle runs north-south.
    assert min(best.travel_axis_deg, 180 - best.travel_axis_deg) < 20


def test_no_saddle_on_a_plain_ridge():
    dem = dem_from(lambda X, Y: 400 + 60 * np.exp(-((Y / 160) ** 2)))
    t = terrain.derive(dem)
    assert not [f for f in terrain.find_features(dem, t) if f.kind == "saddle"]


def test_finds_bench_running_along_the_contour():
    dem = dem_from(hillside_with_bench)
    t = terrain.derive(dem)
    benches = [f for f in terrain.find_features(dem, t) if f.kind == "bench"]
    assert benches, "expected a bench"
    b = max(benches, key=lambda f: f.area_m2)
    assert -10 < b.y < 50
    assert abs(b.travel_axis_deg - 90) < 15  # contour runs east-west


def test_unit_terrain_signals():
    dem = dem_from(hillside_with_bench)
    t = terrain.derive(dem)
    sig = terrain.unit_signals(dem, t, box(-300, -300, 300, 300))
    assert sig["relief_m"] > 100
    assert 15 < sig["mean_slope_deg"] < 30
    assert terrain.unit_signals(dem, t, box(500, 500, 900, 900)) is None  # outside the tile


def test_tile_grid_covers_bounds():
    tiles = terrain.tile_grid((100, 100, 25000, 9000), 8000)
    assert len(tiles) == 4 * 2
    assert tiles[0][0] <= 100 and tiles[-1][2] >= 25000


# ------------------------------------------------------------------ land cover


def lc_raster():
    # 100 x 100 pixels of 30 m: left half deciduous forest, right half evergreen, with a
    # 10-pixel-wide band of shrub/scrub regrowth through the middle and a pond corner.
    a = np.full((100, 100), 41, dtype=np.uint8)
    a[:, 50:] = 42
    a[45:55, :] = 52
    a[:10, :10] = 11
    return LandCover(a, from_origin(0, 3000, 30, 30), "EPSG:5070", "test", 2024, "test")


def test_landcover_shares_and_edges():
    lc = lc_raster()
    st = landcover.unit_stats(lc, box(0, 0, 3000, 3000))
    s = st["lc_shares"]
    assert s["young"] == pytest.approx(1000 / 9900, rel=0.01)  # 10 rows of regrowth, water excluded
    assert st["forest"] == pytest.approx(8900 / 9900, rel=0.01)
    assert st["water"] == 0 if "water" in st else True
    assert s["water"] == pytest.approx(100 / 10000, rel=0.01)
    # Two forest/regrowth boundaries 100 pixels long -> 200 pairs x 30 m over 891 ha
    assert st["edge_m_per_ha"] == pytest.approx(200 * 30 / (9900 * 900 / 10000), rel=0.02)
    assert 0.4 < st["conifer_share_of_forest"] < 0.6


def test_landcover_outside_raster_is_none():
    assert landcover.unit_stats(lc_raster(), box(5000, 5000, 6000, 6000)) is None


def test_picks_newest_annual_land_cover():
    ids = [
        "mrlc__Annual_NLCD_LndCov_2023_CU_C1V1",
        "mrlc__Annual_NLCD_LndCov_2025_CU_C1V2",
        "mrlc__Annual_NLCD_LndChg_2025_CU_C1V2",
        "mrlc__Annual_NLCD_LndCnf_2025_CU_C1V2",
        "mrlc__Annual_NLCD_FctImp_2025_CU_C1V2",
    ]
    assert landcover.pick_annual_coverage(ids) == ("mrlc__Annual_NLCD_LndCov_2025_CU_C1V2", 2025)
    assert landcover.pick_annual_coverage(["something_else"]) is None


def test_parses_coverage_ids_from_capabilities():
    xml = "<wcs:CoverageSummary><wcs:CoverageId>a__LndCov_2024</wcs:CoverageId></wcs:CoverageSummary><CoverageId> b </CoverageId>"
    assert landcover.coverage_ids(xml) == ["a__LndCov_2024", "b"]


def test_validate_counts_real_classes():
    assert landcover.validate(np.array([41, 42, 0, 255], dtype=np.uint8)) == 0.5


def test_tiles_snap_to_grid():
    t = landcover._tiles((15, 15, 100000, 50000), max_px=1500)
    assert t[0][0] == 0 and t[0][1] == 0
    assert all((b[2] - b[0]) <= 45000 for b in t)


# ------------------------------------------------------------------ roads


def test_overpass_parsing_and_gates():
    doc = {
        "elements": [
            {"type": "way", "tags": {"highway": "track", "name": "Indian Stream Rd"}, "geometry": [{"lat": 45.1, "lon": -71.4}, {"lat": 45.2, "lon": -71.4}]},
            {"type": "way", "tags": {"highway": "track", "access": "private"}, "geometry": [{"lat": 45.1, "lon": -71.3}, {"lat": 45.2, "lon": -71.3}]},
            {"type": "node", "lat": 1, "lon": 1},
        ]
    }
    g = roads.parse_overpass(doc)
    assert len(g) == 2
    assert g["gated"].tolist() == [False, True]
    assert "45" in roads.overpass_query((-71.85, 44.2, -70.95, 45.31))


def test_road_signals_for_a_block():
    import geopandas as gpd

    # Road along the bottom edge of a 2 km block; gated road on the far side.
    road = gpd.GeoDataFrame({"name": ["Main Rd"], "source": ["dot"], "gated": [False]}, geometry=[LineString([(0, 0), (2000, 0)])], crs="EPSG:5070")
    gate = gpd.GeoDataFrame({"name": [None], "source": ["osm"], "gated": [True]}, geometry=[LineString([(0, 3000), (2000, 3000)])], crs="EPSG:5070")
    trail = gpd.GeoDataFrame(geometry=[LineString([(1000, 0), (1000, 2000)])], crs="EPSG:5070")
    net = roads.Network.build(gpd.pd.concat([road, gate]), trail)
    sig = roads.unit_signals(net, box(0, 0, 2000, 2000))
    assert sig["road_min_dist_m"] == 0
    assert sig["share_near_road"] == pytest.approx(0.2, abs=0.01)  # bottom 400 m of 2000 m
    assert sig["share_interior"] == pytest.approx(0.6, abs=0.01)  # beyond 800 m
    assert sig["gated_road_min_dist_m"] == pytest.approx(1000)
    assert sig["nearest_road_name"] == "Main Rd"
    assert sig["trail_km_per_km2"] > 0
    far = roads.unit_signals(net, box(5000, 5000, 6000, 6000))
    assert far["road_min_dist_m"] > 3000
    assert far["share_near_road"] == 0


def test_distance_grid_matches_vector_shares():
    import geopandas as gpd

    road = gpd.GeoDataFrame({"name": ["Main Rd"], "source": ["dot"], "gated": [False]}, geometry=[LineString([(0, 0), (2000, 0)])], crs="EPSG:5070")
    net = roads.Network.build(road, None)
    vec = roads.unit_signals(net, box(0, 0, 2000, 2000))
    net.build_distance_grid((0, 0, 2000, 2000), res=10)
    grid = roads.unit_signals(net, box(0, 0, 2000, 2000))
    assert grid["share_near_road"] == pytest.approx(vec["share_near_road"], abs=0.02)
    assert grid["share_interior"] == pytest.approx(vec["share_interior"], abs=0.02)
