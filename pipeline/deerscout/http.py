"""Small HTTP helper with retries, so one flaky request doesn't sink a whole run."""

from __future__ import annotations

import time
from typing import Any, Protocol

import requests

from .config import USER_AGENT


class SourceError(RuntimeError):
    """A data source could not be reached or returned something unusable."""

    def __init__(self, source: str, message: str):
        super().__init__(f"{source}: {message}")
        self.source = source
        self.message = message


class Session(Protocol):
    def get(self, url: str, params: dict[str, Any] | None = None, timeout: float = ...) -> Any: ...


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _read_capped(resp: Any, max_bytes: int | None, source: str) -> bytes:
    """Read a response body, refusing anything larger than max_bytes (protects memory)."""
    if max_bytes is None:
        return resp.content
    length = (getattr(resp, "headers", {}) or {}).get("Content-Length")
    if length and int(length) > max_bytes:
        raise SourceError(source, f"response too large ({int(length) / 1e6:.0f} MB > {max_bytes / 1e6:.0f} MB cap)")
    if hasattr(resp, "iter_content"):
        chunks, total = [], 0
        for chunk in resp.iter_content(chunk_size=1 << 20):
            total += len(chunk)
            if total > max_bytes:
                resp.close()
                raise SourceError(source, f"response exceeded the {max_bytes / 1e6:.0f} MB cap")
            chunks.append(chunk)
        return b"".join(chunks)
    body = resp.content
    if len(body) > max_bytes:
        raise SourceError(source, f"response exceeded the {max_bytes / 1e6:.0f} MB cap")
    return body


def get_bytes(
    session: Session,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    source: str,
    retries: int = 3,
    backoff: float = 2.0,
    timeout: float = 180.0,
    max_bytes: int | None = 200_000_000,
    sleep=time.sleep,
) -> tuple[bytes, str]:
    """GET a binary document (raster, XML). Returns (body, content type).

    Bodies over ``max_bytes`` are refused rather than loaded, so a server that ignores our
    area limits can't exhaust memory.
    """
    last_err = "no attempt made"
    for attempt in range(retries):
        try:
            try:
                resp = session.get(url, params=params, timeout=timeout, stream=True)
            except TypeError:  # simple sessions (tests) don't take `stream`
                resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:
            last_err = f"network error: {exc}"
        else:
            status = getattr(resp, "status_code", 200)
            if status == 429 or status >= 500:
                last_err = f"HTTP {status}"
            elif status >= 400:
                raise SourceError(source, f"HTTP {status} for {url}")
            else:
                ctype = (getattr(resp, "headers", {}) or {}).get("Content-Type", "")
                try:
                    return _read_capped(resp, max_bytes, source), ctype
                except requests.RequestException as exc:
                    last_err = f"network error while reading: {exc}"
        if attempt < retries - 1:
            sleep(backoff * (2**attempt))
    raise SourceError(source, f"gave up after {retries} attempts ({last_err})")


def get_json(
    session: Session,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    source: str,
    retries: int = 3,
    backoff: float = 2.0,
    timeout: float = 60.0,
    sleep=time.sleep,
) -> dict[str, Any]:
    """GET a JSON document. Retries network errors and 5xx/429 responses; fails fast on 4xx."""
    last_err = "no attempt made"
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except requests.RequestException as exc:  # network trouble: retry
            last_err = f"network error: {exc}"
        else:
            status = getattr(resp, "status_code", 200)
            if status == 429 or status >= 500:
                last_err = f"HTTP {status}"
            elif status >= 400:
                raise SourceError(source, f"HTTP {status} for {url}")
            else:
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise SourceError(source, f"response was not JSON: {exc}") from exc
                if isinstance(data, dict) and "error" in data:
                    err = data["error"]
                    msg = err.get("message", err) if isinstance(err, dict) else err
                    raise SourceError(source, f"service error: {msg}")
                return data
        if attempt < retries - 1:
            sleep(backoff * (2**attempt))
    raise SourceError(source, f"gave up after {retries} attempts ({last_err})")
