"""Shared test helpers.

Test fixtures are synthetic shapes used only to exercise the code. They never ship in the
app's data files, which come only from real sources.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import pytest
from pyproj import Transformer
from shapely.geometry import box, mapping
import shapely

# UTM zone 19N covers Coos County; handy for making shapes with exact sizes in meters.
_UTM_TO_WGS = Transformer.from_crs("EPSG:26919", "EPSG:4326", always_xy=True)


def to_wgs(geom):
    """Reproject a shape drawn in UTM 19N meters to WGS84 lon/lat."""
    return shapely.transform(geom, lambda x, y: _UTM_TO_WGS.transform(x, y), interleaved=False)

# A point in Pittsburg, NH in UTM 19N meters (approx. 45.05 N, 71.40 W).
ORIGIN = (310000.0, 4991000.0)


def square_wgs(x0: float, y0: float, side_m: float):
    """A square of known size (meters) placed in UTM, returned in WGS84 lon/lat."""
    return to_wgs(box(x0, y0, x0 + side_m, y0 + side_m))


def feature(geom, **props) -> dict[str, Any]:
    return {"type": "Feature", "geometry": mapping(geom), "properties": props}


class FakeResponse:
    def __init__(self, payload: Any = None, status: int = 200, content: bytes | None = None, ctype: str = "application/json"):
        self._payload = payload
        self.status_code = status
        if content is None:
            content = b"" if isinstance(payload, Exception) else json.dumps(payload).encode()
        self.content = content
        self.headers = {"Content-Type": ctype}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return json.loads(json.dumps(self._payload))


class FakeSession:
    """Routes GET requests to handler functions: handler(url, params) -> FakeResponse."""

    def __init__(self, handler: Callable[[str, dict], FakeResponse]):
        self.handler = handler
        self.calls: list[tuple[str, dict]] = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.handler(url, dict(params or {}))


@pytest.fixture
def no_sleep():
    return lambda s: None
