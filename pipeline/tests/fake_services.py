"""Fake versions of the Phase 2-3 web services for offline end-to-end tests.

They return small synthetic rasters and lines with known shapes. Test-only: never shipped.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timedelta

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import LineString, mapping

from deerscout import landcover, roads, terrain, windhistory

from .conftest import FakeResponse

_EA_TO_WGS = Transformer.from_crs("EPSG:5070", "EPSG:4326", always_xy=True)


def geotiff(arr: np.ndarray, transform, crs="EPSG:5070", dtype=None) -> bytes:
    buf = io.BytesIO()
    with rasterio.io.MemoryFile() as mf:
        with mf.open(driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype=dtype or arr.dtype, crs=crs, transform=transform) as ds:
            ds.write(arr, 1)
        buf.write(mf.read())
    return buf.getvalue()


class Services:
    """Builds fake responses around a center point given in the equal-area system."""

    def __init__(self, center_ea: tuple[float, float]):
        self.cx, self.cy = center_ea

    # ---- land cover: forest with a strip of young regrowth through the center
    def nlcd(self, url, params):
        if params.get("request") == "GetCapabilities":
            xml = "<wcs:Contents><wcs:CoverageSummary><wcs:CoverageId>mrlc__Annual_NLCD_LndCov_2025_CU_C1V2</wcs:CoverageId></wcs:CoverageSummary></wcs:Contents>"
            return FakeResponse(content=xml.encode(), ctype="application/xml")
        xs = [float(v) for v in re.findall(r"[-\d.]+", params["subset"][0])]
        ys = [float(v) for v in re.findall(r"[-\d.]+", params["subset"][1])]
        w, h = int(round((xs[1] - xs[0]) / 30)), int(round((ys[1] - ys[0]) / 30))
        tr = from_origin(xs[0], ys[1], 30, 30)
        cols = xs[0] + 15 + 30 * np.arange(w)
        rows = ys[1] - 15 - 30 * np.arange(h)
        X, Y = np.meshgrid(cols, rows)
        arr = np.where(X < self.cx, 41, 42).astype(np.uint8)
        arr[np.abs(Y - self.cy) < 150] = 52
        return FakeResponse(content=geotiff(arr, tr), ctype="image/tiff")

    # ---- elevation: east-west ridge with a saddle at the center
    def dem(self, url, params):
        minx, miny, maxx, maxy = (float(v) for v in params["bbox"].split(","))
        w, h = (int(v) for v in params["size"].split(","))
        rx, ry = (maxx - minx) / w, (maxy - miny) / h
        X, Y = np.meshgrid(minx + rx * (np.arange(w) + 0.5), maxy - ry * (np.arange(h) + 0.5))
        dx, dy = X - self.cx, Y - (self.cy + 600)
        z = 400 + 60 * np.exp(-((dy / 160) ** 2)) - 25 * np.exp(-((dx / 90) ** 2)) * np.exp(-((dy / 160) ** 2))
        return FakeResponse(content=geotiff(z.astype(np.float32), from_origin(minx, maxy, rx, ry)), ctype="image/tiff")

    # ---- roads and trails
    def _line_wgs(self, x0, y0, x1, y1):
        pts = [_EA_TO_WGS.transform(x, y) for x, y in ((x0, y0), (x1, y1))]
        return LineString(pts)

    def dot_roads(self, url, params):
        if params.get("returnCountOnly") == "true":
            return FakeResponse({"count": 1})
        line = self._line_wgs(self.cx - 20000, self.cy - 2500, self.cx + 20000, self.cy - 2500)
        return FakeResponse({"features": [{"type": "Feature", "geometry": mapping(line), "properties": {"STREET": "Test Rd"}}]})

    def overpass(self, url, params):
        line = self._line_wgs(self.cx - 3000, self.cy + 3000, self.cx + 3000, self.cy + 3000)
        geom = [{"lon": x, "lat": y} for x, y in line.coords]
        return FakeResponse({"elements": [{"type": "way", "tags": {"highway": "track", "name": "Logging Rd"}, "geometry": geom}]})

    def trails(self, url, params):
        if url == roads.TRAILS_SERVICE:
            return FakeResponse({"layers": [{"id": 0, "name": "Trails", "geometryType": "esriGeometryPolyline"}]})
        if url.endswith("/0"):
            return FakeResponse({"maxRecordCount": 1000})
        if params.get("returnCountOnly") == "true":
            return FakeResponse({"count": 1})
        line = self._line_wgs(self.cx + 5000, self.cy - 5000, self.cx + 5000, self.cy + 5000)
        return FakeResponse({"features": [{"type": "Feature", "geometry": mapping(line), "properties": {}}]})

    # ---- historical wind: steady northwest mornings, southwest evenings
    def archive(self, url, params):
        start = datetime.fromisoformat(params["start_date"])
        times, dirs, speeds = [], [], []
        t = start
        while t <= start + timedelta(days=120):
            times.append(t.strftime("%Y-%m-%dT%H:%M"))
            dirs.append(315.0 if t.hour < 12 else 225.0)
            speeds.append(6.0)
            t += timedelta(hours=1)
        return FakeResponse({"latitude": params["latitude"], "longitude": params["longitude"], "elevation": 500, "hourly": {"time": times, "wind_direction_10m": dirs, "wind_speed_10m": speeds}})

    def route(self, url, params):
        if url == landcover.DMS_WCS:
            return self.nlcd(url, params)
        if url == terrain.IMAGE_SERVER:
            return self.dem(url, params)
        if url.startswith(roads.DOT_ROADS):
            if url == roads.DOT_ROADS:
                return FakeResponse({"maxRecordCount": 2000})
            return self.dot_roads(url, params)
        if url in roads.OVERPASS:
            return self.overpass(url, params)
        if url.startswith(roads.TRAILS_SERVICE):
            return self.trails(url, params)
        if url == windhistory.ARCHIVE:
            return self.archive(url, params)
        return None
