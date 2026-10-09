"""Explainable Property Quality Score (0-100).

Each factor produces a 0-100 value (or None when its data isn't available), a confidence,
plain-language evidence, and a label for what kind of claim it is. The overall score is the
weighted average of the factors that have data; the share of weight that had data is
reported as ``coverage`` so a score built on thin evidence is never presented as complete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

FACTOR_LABELS = {
    "habitat": "Habitat, food and cover",
    "pressure": "Estimated hunting pressure",
    "terrain": "Terrain and travel features",
    "access": "Access and huntability",
    "abundance": "Regional deer abundance",
}

# What kind of claim a factor value rests on (shown in the app).
BASIS = {
    "fact": "Directly mapped fact",
    "supported": "Supported by published research",
    "heuristic": "Engineering heuristic",
    "assumption": "Unverified assumption",
    "missing": "Missing information",
}

CONFIDENCE_ORDER = ["none", "low", "medium", "high"]


@dataclass
class FactorResult:
    key: str
    value: float | None
    confidence: str
    basis: str
    evidence: list[str] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, weight: float) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": FACTOR_LABELS[self.key],
            "value": None if self.value is None else round(self.value, 1),
            "weight": weight,
            "confidence": self.confidence,
            "basis": self.basis,
            "basis_label": BASIS[self.basis],
            "evidence": self.evidence,
            "signals": self.signals,
        }


@dataclass
class ScoreResult:
    score: float | None
    coverage: float
    provisional: bool
    confidence: str
    factors: list[dict[str, Any]]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": None if self.score is None else round(self.score),
            "coverage": round(self.coverage, 3),
            "provisional": self.provisional,
            "confidence": self.confidence,
            "factors": self.factors,
            "summary": self.summary,
        }


def ramp(x: float | None, lo: float, hi: float) -> float | None:
    """0 at or below lo, 1 at or above hi, linear between."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if hi == lo:
        return 1.0 if x >= hi else 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


def log_ramp(x: float | None, lo: float, hi: float) -> float | None:
    if x is None or x <= 0:
        return None if x is None else 0.0
    return ramp(math.log10(x), math.log10(lo), math.log10(hi))


def load_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text())
    validate_weights(cfg["weights"])
    return cfg


def validate_weights(weights: dict[str, float]) -> None:
    missing = set(FACTOR_LABELS) - set(weights)
    if missing:
        raise ValueError(f"missing weights for {sorted(missing)}")
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must not be negative")
    if sum(weights.values()) <= 0:
        raise ValueError("weights must add up to more than zero")


# ---------------------------------------------------------------- factors


def access_factor(signals: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
    c = cfg["access"]
    size = log_ramp(signals.get("acres"), c["size_floor_acres"], c["size_full_acres"])
    shape = ramp(signals.get("compactness"), c["shape_floor"], c["shape_full"])
    if size is None:
        return FactorResult("access", None, "none", "missing", ["Area could not be measured."])
    parts = [(size, c["size_share"])]
    if shape is not None:
        parts.append((shape, c["shape_share"]))
    value = 100 * sum(v * w for v, w in parts) / sum(w for _, w in parts)
    ev = [f"{signals['acres']:,.0f} acres in this unit."]
    if shape is not None:
        if shape < 0.3:
            ev.append("Long or narrow shape: easy to wander over a boundary.")
        elif shape > 0.8:
            ev.append("Compact shape: room to set up away from edges.")
    road = signals.get("road_access")
    if road is None:
        ev.append("Road and trailhead access not analyzed yet.")
        conf = "low"
    else:
        conf = "medium"
    acc = signals.get("boundary_accuracy_code")
    if acc in (3, 4, 5):
        ev.append("Mapped boundary accuracy is only fair/poor; actual lines may differ.")
    return FactorResult("access", value, conf, "heuristic", ev, {"size": size, "shape": shape})


def _missing(key: str, why: str) -> Callable[[dict[str, Any], dict[str, Any]], FactorResult]:
    def f(signals: dict[str, Any], cfg: dict[str, Any]) -> FactorResult:
        return FactorResult(key, None, "none", "missing", [why])

    return f


FACTORS: dict[str, Callable[[dict[str, Any], dict[str, Any]], FactorResult]] = {
    "habitat": _missing("habitat", "Land cover hasn't been analyzed for this unit yet."),
    "pressure": _missing("pressure", "Roads, trails and parking haven't been analyzed yet."),
    "terrain": _missing("terrain", "LiDAR terrain hasn't been analyzed for this unit yet."),
    "access": access_factor,
    "abundance": _missing("abundance", "Deer harvest data hasn't been loaded yet."),
}


def register(key: str, fn: Callable[[dict[str, Any], dict[str, Any]], FactorResult]) -> None:
    """Later phases plug in real factor functions here."""
    if key not in FACTOR_LABELS:
        raise KeyError(key)
    FACTORS[key] = fn


def combine(results: list[FactorResult], weights: dict[str, float], provisional_below: float = 0.5) -> ScoreResult:
    validate_weights(weights)
    total_w = sum(weights[r.key] for r in results)
    have = [r for r in results if r.value is not None and weights[r.key] > 0]
    have_w = sum(weights[r.key] for r in have)
    coverage = have_w / total_w if total_w else 0.0
    if have_w == 0:
        score = None
    else:
        score = sum(r.value * weights[r.key] for r in have) / have_w  # type: ignore[operator]

    if not have:
        confidence = "none"
    else:
        lowest = min(CONFIDENCE_ORDER.index(r.confidence) for r in have)
        cap = 1 if coverage < provisional_below else 2 if coverage < 0.85 else 3
        confidence = CONFIDENCE_ORDER[max(1, min(lowest, cap))]

    provisional = coverage < provisional_below
    if score is None:
        summary = "Not enough data to score yet."
    else:
        missing = [FACTOR_LABELS[r.key].lower() for r in results if r.value is None]
        summary = f"Based on {coverage:.0%} of the model."
        if missing:
            summary += " Not yet included: " + ", ".join(missing) + "."
    return ScoreResult(
        score=score,
        coverage=coverage,
        provisional=provisional,
        confidence=confidence,
        factors=[r.to_dict(weights[r.key]) for r in results],
        summary=summary,
    )


def score_unit(signals: dict[str, Any], cfg: dict[str, Any]) -> ScoreResult:
    results = [FACTORS[k](signals, cfg) for k in FACTOR_LABELS]
    return combine(results, cfg["weights"], cfg.get("provisional_below_coverage", 0.5))
