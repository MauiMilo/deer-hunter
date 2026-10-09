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
    confidence: str  # "town-wide" | "split-town" | "unknown"
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
