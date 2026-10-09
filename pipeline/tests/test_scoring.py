import pytest

from deerscout.config import PIPELINE_DIR
from deerscout.scoring import (
    FactorResult,
    combine,
    load_config,
    log_ramp,
    ramp,
    score_unit,
    validate_weights,
)

W = {"habitat": 0.35, "pressure": 0.20, "terrain": 0.20, "access": 0.15, "abundance": 0.10}


def fr(key, value, conf="high", basis="fact"):
    return FactorResult(key, value, conf, basis if value is not None else "missing", ["x"])


def test_weighted_average_with_all_factors():
    res = combine([fr("habitat", 80), fr("pressure", 60), fr("terrain", 40), fr("access", 100), fr("abundance", 50)], W)
    expected = 80 * 0.35 + 60 * 0.2 + 40 * 0.2 + 100 * 0.15 + 50 * 0.1
    assert res.score == pytest.approx(expected)
    assert res.coverage == pytest.approx(1.0)
    assert not res.provisional
    assert res.confidence == "high"


def test_missing_factors_are_excluded_not_counted_as_zero():
    res = combine([fr("habitat", 80), fr("pressure", None), fr("terrain", None), fr("access", 40), fr("abundance", None)], W)
    assert res.score == pytest.approx((80 * 0.35 + 40 * 0.15) / 0.5)
    assert res.coverage == pytest.approx(0.5)


def test_low_coverage_is_provisional_and_low_confidence():
    res = combine([fr("habitat", None), fr("pressure", None), fr("terrain", None), fr("access", 90), fr("abundance", None)], W)
    assert res.score == pytest.approx(90)
    assert res.coverage == pytest.approx(0.15)
    assert res.provisional
    assert res.confidence == "low"
    assert "15%" in res.summary
    assert "habitat" in res.summary


def test_no_data_gives_no_score():
    res = combine([fr(k, None) for k in W], W)
    assert res.score is None
    assert res.confidence == "none"


def test_confidence_capped_by_weakest_factor():
    res = combine([fr("habitat", 50, "low"), fr("pressure", 50), fr("terrain", 50), fr("access", 50), fr("abundance", 50)], W)
    assert res.confidence == "low"


def test_zero_weight_factor_ignored():
    w = dict(W, habitat=0.0)
    res = combine([fr("habitat", 0), fr("pressure", 100), fr("terrain", 100), fr("access", 100), fr("abundance", 100)], w)
    assert res.score == pytest.approx(100)


@pytest.mark.parametrize(
    "bad",
    [
        {"habitat": 1},
        dict(W, habitat=-0.1),
        {k: 0 for k in W},
    ],
)
def test_bad_weights_rejected(bad):
    with pytest.raises(ValueError):
        validate_weights(bad)


def test_ramps():
    assert ramp(5, 0, 10) == 0.5
    assert ramp(-1, 0, 10) == 0.0
    assert ramp(11, 0, 10) == 1.0
    assert ramp(None, 0, 10) is None
    assert log_ramp(100, 10, 1000) == pytest.approx(0.5)
    assert log_ramp(0, 10, 1000) == 0.0


def test_shipped_config_scores_a_unit():
    cfg = load_config(PIPELINE_DIR / "data" / "scoring.yaml")
    assert sum(cfg["weights"].values()) == pytest.approx(1.0)
    small = score_unit({"acres": 30, "compactness": 0.6}, cfg)
    big = score_unit({"acres": 1200, "compactness": 0.6}, cfg)
    assert big.score > small.score
    assert big.provisional  # only the access factor has data so far
    keys = [f["key"] for f in big.factors]
    assert keys == ["habitat", "pressure", "terrain", "access", "abundance"]
    assert all(f["basis"] == "missing" for f in big.factors if f["key"] != "access")
