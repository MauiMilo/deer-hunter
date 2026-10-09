"""Read features from ArcGIS REST map/feature services as GeoJSON, with paging and provenance."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .http import Session, SourceError, get_json


@dataclass
class FetchResult:
    features: list[dict[str, Any]]
    source: str
    url: str
    params: dict[str, Any]
    retrieved_at: str
    pages: int
    expected_count: int | None = None
    warnings: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def layer_info(session: Session, layer_url: str, *, source: str) -> dict[str, Any]:
    return get_json(session, layer_url, {"f": "json"}, source=source)


def query_geojson(
    session: Session,
    layer_url: str,
    *,
    source: str,
    where: str = "1=1",
    envelope: tuple[float, float, float, float] | None = None,
    out_fields: str = "*",
    page_size: int | None = None,
    max_pages: int = 200,
    extra: dict[str, Any] | None = None,
) -> FetchResult:
    """Fetch every feature matching the query, paging with resultOffset.

    Geometry comes back in WGS84 (outSR=4326). If the service won't page, we stop and
    report a warning rather than silently returning a truncated set.
    """
    base: dict[str, Any] = {
        "where": where,
        "outFields": out_fields,
        "returnGeometry": "true",
        "outSR": 4326,
        "f": "geojson",
    }
    if envelope is not None:
        base.update(
            {
                "geometry": ",".join(str(v) for v in envelope),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            }
        )
    if extra:
        base.update(extra)

    count_params = {k: v for k, v in base.items() if k not in ("outFields", "returnGeometry", "outSR")}
    count_params.update({"returnCountOnly": "true", "f": "json"})
    expected = get_json(session, f"{layer_url}/query", count_params, source=source).get("count")

    if page_size is None:
        info = layer_info(session, layer_url, source=source)
        page_size = int(info.get("maxRecordCount") or 1000)

    features: list[dict[str, Any]] = []
    warnings: list[str] = []
    pages = 0
    offset = 0
    while pages < max_pages:
        params = dict(base, resultOffset=offset, resultRecordCount=page_size)
        if "orderByFields" not in params:
            params["orderByFields"] = "OBJECTID"
        page = get_json(session, f"{layer_url}/query", params, source=source)
        pages += 1
        batch = page.get("features") or []
        features.extend(batch)
        more = bool(page.get("exceededTransferLimit")) or (
            page.get("properties", {}) or {}
        ).get("exceededTransferLimit", False)
        if not batch:
            break
        if expected is not None and len(features) >= expected:
            break
        if not more and len(batch) < page_size:
            break
        offset += len(batch)
    else:
        warnings.append(f"stopped after {max_pages} pages; results may be incomplete")

    if expected is not None and len(features) != expected:
        msg = f"service reported {expected} features but {len(features)} were downloaded"
        if len(features) < expected:
            raise SourceError(source, msg)
        warnings.append(msg)

    return FetchResult(
        features=features,
        source=source,
        url=f"{layer_url}/query",
        params=base,
        retrieved_at=_now(),
        pages=pages,
        expected_count=expected,
        warnings=warnings,
    )
