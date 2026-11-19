"""The list of regions the app can show (web/public/data/regions.json).

Each region's data lives in its own folder, web/public/data/<slug>/. This list only changes when
a region is added in config.py, never during a data build, so builds of different regions can't
overwrite each other's entries. A test checks it matches config.py.

    python -m deerscout.regions          # rewrite regions.json after changing config.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .config import OUTPUT_DIR, REGIONS, Region

DEFAULT_REGION = "coos"
INDEX_PATH = OUTPUT_DIR / "regions.json"


def entry(region: Region) -> dict[str, Any]:
    w, s, e, n = region.envelope
    center = region.map_center or region.center or ((w + e) / 2, (s + n) / 2)
    label, lon, lat = region.home
    return {
        "slug": region.slug,
        "name": region.name,
        "short_name": region.short_name,
        "path": f"/data/{region.slug}/",
        "center": [round(center[0], 5), round(center[1], 5)],
        "bbox": [w, s, e, n],
        "home": {"label": label, "lon": lon, "lat": lat},
    }


def index() -> dict[str, Any]:
    return {"default": DEFAULT_REGION, "regions": [entry(r) for r in REGIONS.values()]}


def render() -> str:
    return json.dumps(index(), indent=2, ensure_ascii=False) + "\n"


def write(path: Path = INDEX_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render())
    return path


if __name__ == "__main__":
    print(f"wrote {write()}")
    sys.exit(0)
