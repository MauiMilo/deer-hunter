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
    """A study area.

    The conservation, WMU, road and trail queries use the envelope. Results are clipped to the
    region's shape: the whole county when there is one county and no radius, otherwise the whole
    towns (from ``counties``) whose Census internal point lies within ``radius_miles`` of ``center``.
    """

    slug: str
    name: str
    short_name: str  # what the app's region switcher shows
    counties: tuple[str, ...]  # Census county GEOIDs (state FIPS + county FIPS) to draw towns from
    envelope: tuple[float, float, float, float]  # lon_min, lat_min, lon_max, lat_max (WGS84)
    home: tuple[str, float, float]  # default starting point in the app: label, lon, lat
    focus_towns: tuple[str, ...] = ()
    center: tuple[float, float] | None = None  # lon, lat
    radius_miles: float | None = None
    map_center: tuple[float, float] | None = None  # where the app's map opens (lon, lat); default: center

    @property
    def by_radius(self) -> bool:
        return self.radius_miles is not None and self.center is not None

    @property
    def county_geoid(self) -> str:
        """The single county of a one-county region."""
        if len(self.counties) != 1 or self.by_radius:
            raise ValueError(f"region {self.slug} is not a single county")
        return self.counties[0]


COOS = Region(
    slug="coos",
    name="Coos County, NH",
    short_name="Coos",
    counties=("33007",),
    envelope=(-71.85, 44.20, -70.95, 45.31),
    home=("Pittsburg village", -71.3912, 45.0515),
    focus_towns=("Pittsburg", "Clarksville", "Stewartstown"),
    map_center=(-71.3, 45.05),  # the app's map has always opened here
)

# Concord area: about an hour's drive from Concord, across county lines. There's no drive-time
# service, so "an hour" is approximated as whole towns whose center (Census internal point) is
# within 30 straight-line miles of the State House; on NH roads that's usually 45-65 minutes.
# That gives 82 towns in six counties (checked against TIGERweb on 2026-11-18), including Weare
# and the Hillsborough County side of the Hopkinton-Everett project. The envelope is those towns'
# bounding box plus a small margin.
CONCORD = Region(
    slug="concord",
    name="Concord area, NH (towns within 30 miles of Concord)",
    short_name="Concord area",
    # Belknap, Hillsborough, Merrimack, Rockingham, Strafford, Sullivan
    counties=("33001", "33011", "33013", "33015", "33017", "33019"),
    envelope=(-72.19, 42.75, -70.88, 43.71),
    home=("Concord (State House)", -71.5381, 43.2067),
    focus_towns=("Concord", "Hopkinton", "Dunbarton", "Weare", "Allenstown", "Pembroke", "Bow", "Hooksett"),
    center=(-71.5381, 43.2067),
    radius_miles=30.0,
)

REGIONS = {COOS.slug: COOS, CONCORD.slug: CONCORD}

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
