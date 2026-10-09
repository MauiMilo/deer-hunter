"""Wildlife Management Unit (WMU) lookup by town.

No official WMU GIS layer was found yet, so units come from the digest's written boundary
descriptions (roads and rivers). Towns that a boundary road cuts through are marked "split";
the app then shows the shorter of the possible seasons and asks you to check the boundary.

Source: 2026-27 NH Hunting Digest, Wildlife Management Units page (retrieved 2026-10-08).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Places wholly on one side of the WMU A southern boundary (Rt 26 / Rt 3 / Lemington Rd),
# or wholly inside WMU B (north of Rt 110, west of Rt 16). Keys are normalized names.
_WHOLE = {
    "pittsburg": "A",
    "clarksville": "A",
    "stewartstown": "A",
    "second college": "A",
    "atkinson and gilmanton": "A",
    "dixs": "A",
    "columbia": "B",
    "stratford": "B",
    "odell": "B",
}

# Places crossed by a boundary road.
_SPLIT = {
    "colebrook": ("A", "B", "The WMU A/B line follows Rt 26 and Rt 3 / Lemington Rd through Colebrook."),
    "errol": ("A", "B", "The WMU A/B line follows Rt 26 and Rt 16 through Errol."),
    "dixville": ("A", "B", "The WMU A/B line follows Rt 26 through Dixville."),
    "millsfield": ("A", "B", "Check which side of Rt 26 you are on."),
    "wentworths": ("A", "C2", "WMU A ends at Rt 16; C2 lies east of Rt 16."),
    "dummer": ("B", "C2", "The WMU B/C2 line follows Rt 16 and Rt 110-A."),
    "milan": ("B", "C1", "The WMU B/C1 line follows Rt 110."),
    "stark": ("B", "C1", "The WMU B/C1 line follows Rt 110."),
    "northumberland": ("B", "C1", "The WMU B/C1 line follows Rt 3, Rt 110 and Lost Nation Rd."),
    "berlin": ("C1", "C2", "The WMU C1/C2 line follows Rt 16."),
    "gorham": ("C1", "C2", "The WMU C1/C2 line follows Rt 16 and Rt 2."),
    "jefferson": ("C1", "D1", "Boundary roads cross Jefferson, where C1, D1 and E meet."),
}

_SUFFIX = re.compile(r"\s+(township|town|city|grant|purchase|location|academy)$")


def normalize(town: str | None) -> str:
    if not town:
        return ""
    t = town.lower().replace("'", "").replace("’", "").replace("&", "and")
    t = re.sub(r"\s+", " ", t).strip()
    while True:
        new = _SUFFIX.sub("", t)
        if new == t:
            return t
        t = new


@dataclass(frozen=True)
class WmuResult:
    units: tuple[str, ...]
    # "mapped" / "split-mapped" come from the official WMU layer; the town-based values are a fallback.
    confidence: str  # "mapped" | "split-mapped" | "town-wide" | "split-town" | "unknown"
    note: str

    def to_dict(self) -> dict:
        return {"units": list(self.units), "confidence": self.confidence, "note": self.note}


def lookup(town: str | None) -> WmuResult:
    t = normalize(town)
    if t in _WHOLE:
        return WmuResult((_WHOLE[t],), "town-wide", f"All of {town} lies in WMU {_WHOLE[t]}.")
    if t in _SPLIT:
        a, b, note = _SPLIT[t]
        return WmuResult((a, b), "split-town", note)
    return WmuResult((), "unknown", f"WMU for {town or 'this spot'} isn't mapped yet; check the digest map.")


# --------------------------------------------------------------- official WMU layer

WMU_LAYER = "https://services8.arcgis.com/hg1B9Egwk1I5p300/arcgis/rest/services/WMU/FeatureServer/0"
SOURCE_WMU = "NH Fish and Game Wildlife Management Units"


_SUBUNIT = re.compile(r"^([A-Z])\d+$")


def regulation_unit(code: str, known: set[str] | None) -> str:
    """Map a WMU map code to the unit the deer regulations use.

    The WMU layer's own description says a regulation that names a letter alone (e.g. "A")
    covers every numbered unit with that letter (A1, A2). Codes the regulations name exactly
    (C1, C2, D1, D2E ...) are kept as they are.
    """
    code = code.strip().upper()
    if not known or code in known:
        return code
    m = _SUBUNIT.match(code)
    if m and m.group(1) in known:
        return m.group(1)
    return code


def from_layer(unit_geoms, wmu_gdf, min_share: float = 0.02, known_units: set[str] | None = None) -> list[WmuResult]:
    """Deer WMU(s) for each unit polygon by overlaying the official WMU map.

    Both inputs must be GeoSeries/GeoDataFrames in the same projected (equal-area) system.
    A unit is "split" when more than ``min_share`` of its area falls in a second unit.
    """
    col = "WMUDEER" if "WMUDEER" in wmu_gdf.columns else "WMU"
    sindex = wmu_gdf.sindex
    codes = [regulation_unit(c, known_units) for c in wmu_gdf[col].astype(str)]
    geoms = wmu_gdf.geometry.values
    out: list[WmuResult] = []
    for g in unit_geoms:
        shares: dict[str, float] = {}
        if g is not None and not g.is_empty and g.area > 0:
            for j in sindex.query(g, predicate="intersects"):
                a = g.intersection(geoms[j]).area / g.area
                if a > 0:
                    shares[codes[j]] = shares.get(codes[j], 0.0) + a
        units = tuple(sorted((k for k, v in shares.items() if v >= min_share and k and k not in ('None', 'nan')), key=lambda k: -shares[k]))
        if not units:
            out.append(WmuResult((), "unknown", "Outside the mapped WMUs; check the digest map."))
        elif len(units) == 1:
            out.append(WmuResult(units, "mapped", f"Inside WMU {units[0]} (NH Fish and Game WMU map)."))
        else:
            out.append(
                WmuResult(units, "split-mapped", f"This area straddles the WMU {'/'.join(units)} line; check which side you hunt.")
            )
    return out
