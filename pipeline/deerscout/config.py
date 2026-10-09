"""Region, coordinate systems, file locations and service endpoints.

Everything that would change when the app expands to a new county lives here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = PIPELINE_DIR.parent
DATA_DIR = PIPELINE_DIR / "data"  # hand-maintained inputs (rules, regulations, verifications)
CACHE_DIR = PIPELINE_DIR / ".cache"  # raw downloads; never committed
OUTPUT_DIR = REPO_DIR / "web" / "public" / "data"  # what the app reads

# Coordinate systems
WGS84 = "EPSG:4326"  # what web maps and GPS use
EQUAL_AREA = "EPSG:5070"  # NAD83 / CONUS Albers: preserves area, used for acreage
NH_STATE_PLANE = "EPSG:3437"  # NAD83 / New Hampshire (ftUS): GRANIT's native system

SQ_METERS_PER_ACRE = 4046.8564224

USER_AGENT = "deer-scout/0.1 (personal hunting research tool; github.com/MauiMilo/deer-hunter)"


@dataclass(frozen=True)
class Region:
    """A study area. The conservation query uses the envelope; results are clipped to the county shape."""

    slug: str
    name: str
    county_geoid: str  # Census county GEOID (state FIPS + county FIPS)
    envelope: tuple[float, float, float, float]  # lon_min, lat_min, lon_max, lat_max (WGS84)
    focus_towns: tuple[str, ...] = ()


COOS = Region(
    slug="coos",
    name="Coos County, NH",
    county_geoid="33007",
    envelope=(-71.85, 44.20, -70.95, 45.31),
    focus_towns=("Pittsburg", "Clarksville", "Stewartstown"),
)

REGIONS = {COOS.slug: COOS}

# Service endpoints (see DATA_SOURCES.md for verification notes)
CONSERVATION_LAYER = (
    "https://nhgeodata.unh.edu/nhgeodata/rest/services/EC/Conservation/MapServer/1"
)
TIGERWEB_COUNTIES = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1"
)
TIGERWEB_COUSUB_SERVICE = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer"
)

# Large properties are split into blocks this size for ranking (acres, approximate).
BLOCK_TARGET_ACRES = 1000.0
BLOCK_SPLIT_THRESHOLD_ACRES = 3000.0

# Geometry simplification for the map file (meters, in the equal-area system).
SIMPLIFY_TOLERANCE_M = 8.0
COORD_DECIMALS = 5  # ~1 m at this latitude
