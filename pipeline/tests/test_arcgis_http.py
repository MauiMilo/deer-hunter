import pytest
import requests

from deerscout.arcgis import query_geojson
from deerscout.http import SourceError, get_json

from .conftest import FakeResponse, FakeSession, feature, square_wgs, ORIGIN

LAYER = "https://example.test/arcgis/rest/services/X/MapServer/1"


def paged_handler(features, page_limit):
    def handler(url, params):
        if url == LAYER:
            return FakeResponse({"maxRecordCount": page_limit})
        if params.get("returnCountOnly") == "true":
            return FakeResponse({"count": len(features)})
        off = int(params["resultOffset"])
        n = int(params["resultRecordCount"])
        batch = features[off : off + n]
        return FakeResponse(
            {"type": "FeatureCollection", "features": batch, "exceededTransferLimit": off + n < len(features)}
        )

    return handler


def test_query_pages_through_all_features():
    feats = [feature(square_wgs(ORIGIN[0] + i * 2000, ORIGIN[1], 500), OBJECTID=i) for i in range(23)]
    s = FakeSession(paged_handler(feats, 10))
    res = query_geojson(s, LAYER, source="test", envelope=(-72, 44, -71, 45))
    assert len(res.features) == 23
    assert res.pages == 3
    assert res.expected_count == 23
    q = [p for u, p in s.calls if u.endswith("/query") and "resultOffset" in p]
    assert [p["resultOffset"] for p in q] == [0, 10, 20]
    assert q[0]["outSR"] == 4326 and q[0]["inSR"] == 4326


def test_truncated_download_raises():
    feats = [feature(square_wgs(*ORIGIN, 100), OBJECTID=i) for i in range(5)]

    def handler(url, params):
        if params.get("returnCountOnly") == "true":
            return FakeResponse({"count": 9})
        return FakeResponse({"features": feats, "exceededTransferLimit": False})

    with pytest.raises(SourceError, match="reported 9"):
        query_geojson(FakeSession(handler), LAYER, source="test", page_size=10)


def test_service_error_body_raises():
    s = FakeSession(lambda u, p: FakeResponse({"error": {"code": 400, "message": "Invalid query"}}))
    with pytest.raises(SourceError, match="Invalid query"):
        get_json(s, LAYER, source="test")


def test_retries_server_errors_then_succeeds(no_sleep):
    answers = [FakeResponse({}, 503), FakeResponse({}, 500), FakeResponse({"ok": True})]
    s = FakeSession(lambda u, p: answers.pop(0))
    assert get_json(s, LAYER, source="test", sleep=no_sleep) == {"ok": True}
    assert len(s.calls) == 3


def test_gives_up_after_retries(no_sleep):
    s = FakeSession(lambda u, p: FakeResponse({}, 502))
    with pytest.raises(SourceError, match="gave up after 3"):
        get_json(s, LAYER, source="test", sleep=no_sleep)


def test_client_error_fails_fast(no_sleep):
    s = FakeSession(lambda u, p: FakeResponse({}, 404))
    with pytest.raises(SourceError, match="HTTP 404"):
        get_json(s, LAYER, source="test", sleep=no_sleep)
    assert len(s.calls) == 1


def test_network_error_is_retried(no_sleep):
    calls = {"n": 0}

    def handler(u, p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.ConnectionError("boom")
        return FakeResponse({"ok": 1})

    assert get_json(FakeSession(handler), LAYER, source="test", sleep=no_sleep) == {"ok": 1}


def test_non_json_response_raises():
    s = FakeSession(lambda u, p: FakeResponse(ValueError("not json")))
    with pytest.raises(SourceError, match="not JSON"):
        get_json(s, LAYER, source="test")
